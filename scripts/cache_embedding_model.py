"""Download model files at build time without loading PyTorch into memory."""
import os
import sys
from pathlib import Path

from huggingface_hub import snapshot_download


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    if os.environ.get("EMBEDDING_BACKEND") == "onnx":
        sys.path.insert(0, str(root))
        from assistant_app.services.embeddings import ONNX_REPO, ONNX_REVISION, ONNX_FILES
        snapshot_download(repo_id=ONNX_REPO, revision=ONNX_REVISION,
                          cache_dir=str(root / ".cache" / "models"), allow_patterns=ONNX_FILES)
    else:
        snapshot_download(
            repo_id=os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-small"),
            cache_dir=str(root / ".cache" / "models"),
            allow_patterns=["*.json", "*.txt", "*.model", "*.safetensors"],
        )
    print("Embedding model files cached for deployment.")
