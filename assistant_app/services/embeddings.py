import hashlib
from functools import lru_cache
from pathlib import Path
from threading import Lock

from django.conf import settings

_model_lock = Lock()
ONNX_REPO = "Xenova/multilingual-e5-small"
ONNX_REVISION = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"
ONNX_FILES = ["tokenizer.json", "onnx/model_int8.onnx"]


def index_signature():
    # Version the entire embedding space and chunking policy, even for equal dimensions.
    config = f"v3:{settings.EMBEDDING_MODEL}:{settings.EMBEDDING_MAX_TOKENS}:{settings.RAG_CHUNK_SIZE}:{settings.RAG_CHUNK_OVERLAP}"
    if settings.EMBEDDING_BACKEND == "onnx":
        config += f":onnx-int8:{ONNX_REVISION}"
    return hashlib.sha256(config.encode()).hexdigest()


class OnnxEmbedder:
    """Pinned multilingual E5 weights, without importing PyTorch in a small host."""

    def __init__(self, max_tokens):
        import onnxruntime as ort
        from huggingface_hub import snapshot_download
        from tokenizers import Tokenizer

        options = dict(repo_id=ONNX_REPO, revision=ONNX_REVISION,
                       cache_dir=str(settings.BASE_DIR / ".cache" / "models"), allow_patterns=ONNX_FILES)
        try:
            snapshot = Path(snapshot_download(**options, local_files_only=True))
            if not all((snapshot / file).is_file() for file in ONNX_FILES):
                raise FileNotFoundError
        except (OSError, ValueError):
            snapshot = Path(snapshot_download(**options))
        self.max_seq_length = min(max_tokens, 512)
        self.tokenizer = Tokenizer.from_file(str(snapshot / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=self.max_seq_length)
        self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = 1
        session_options.inter_op_num_threads = 1
        session_options.enable_cpu_mem_arena = False
        session_options.enable_mem_pattern = False
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        self.session = ort.InferenceSession(str(snapshot / "onnx/model_int8.onnx"),
                                           sess_options=session_options, providers=["CPUExecutionProvider"])
        self.input_names = {item.name for item in self.session.get_inputs()}
        self.lock = Lock()

    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False, batch_size=2):
        import numpy as np

        vectors = []
        step = max(1, min(batch_size, 2))
        # Serial inference and small batches keep simultaneous uploads/queries bounded.
        with self.lock:
            for start in range(0, len(texts), step):
                batch = self.tokenizer.encode_batch(texts[start:start + step])
                ids = np.asarray([item.ids for item in batch], dtype=np.int64)
                mask = np.asarray([item.attention_mask for item in batch], dtype=np.int64)
                inputs = {"input_ids": ids, "attention_mask": mask}
                if "token_type_ids" in self.input_names:
                    inputs["token_type_ids"] = np.zeros_like(ids)
                states = self.session.run(None, inputs)[0]
                weights = mask[..., None].astype(np.float32)
                pooled = (states * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1)
                if normalize_embeddings:
                    pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
                vectors.extend(pooled)
        return np.asarray(vectors, dtype=np.float32).reshape(-1, 384)


@lru_cache(maxsize=2)
def _load_onnx(max_tokens):
    return OnnxEmbedder(max_tokens)


@lru_cache(maxsize=2)
def _load_model(name, max_tokens):
    from sentence_transformers import SentenceTransformer
    cache = settings.BASE_DIR / ".cache" / "models"
    model = None
    # Read complete cached snapshots directly: repeated server starts then work offline
    # and do not perform Hugging Face HEAD requests or re-download a model.
    for root in [cache, Path.home() / ".cache" / "huggingface" / "hub"]:
        hub = root / ("models--" + name.replace("/", "--"))
        ref = hub / "refs" / "main"
        if not ref.is_file():
            continue
        snapshot = hub / "snapshots" / ref.read_text().strip()
        required = ["modules.json", "config.json", "tokenizer.json", "1_Pooling/config.json"]
        if all((snapshot / file).is_file() for file in required) and any((snapshot / file).is_file() for file in ["model.safetensors", "pytorch_model.bin"]):
            model = SentenceTransformer(str(snapshot), local_files_only=True, trust_remote_code=False)
            break
    if model is None:
        model = SentenceTransformer(name, cache_folder=str(cache), trust_remote_code=False)
    # The multilingual model defaults to 128 tokens, truncating ordinary 900-character
    # chunks. Its encoder supports up to 512; make this explicit and version the index.
    model.max_seq_length = min(max_tokens, model[0].auto_model.config.max_position_embeddings)
    return model


def get_embedder():
    with _model_lock:
        if settings.EMBEDDING_BACKEND == "onnx":
            if settings.EMBEDDING_MODEL != "intfloat/multilingual-e5-small":
                raise ValueError("The ONNX backend requires intfloat/multilingual-e5-small.")
            return _load_onnx(settings.EMBEDDING_MAX_TOKENS)
        return _load_model(settings.EMBEDDING_MODEL, settings.EMBEDDING_MAX_TOKENS)
