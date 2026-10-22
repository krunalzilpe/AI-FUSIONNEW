import hashlib
import json
from functools import lru_cache
from pathlib import Path
from threading import Lock

from django.conf import settings

_model_lock = Lock()


def index_signature():
    # Version the entire embedding space and chunking policy, even for equal dimensions.
    config = f"v3:{settings.EMBEDDING_MODEL}:{settings.EMBEDDING_MAX_TOKENS}:{settings.RAG_CHUNK_SIZE}:{settings.RAG_CHUNK_OVERLAP}"
    return hashlib.sha256(config.encode()).hexdigest()


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
            model = SentenceTransformer(str(snapshot), local_files_only=True)
            break
    if model is None:
        model = SentenceTransformer(name, cache_folder=str(cache))
    # The multilingual model defaults to 128 tokens, truncating ordinary 900-character
    # chunks. Its encoder supports up to 512; make this explicit and version the index.
    model.max_seq_length = min(max_tokens, model[0].auto_model.config.max_position_embeddings)
    return model


def get_embedder():
    with _model_lock:
        return _load_model(settings.EMBEDDING_MODEL, settings.EMBEDDING_MAX_TOKENS)
