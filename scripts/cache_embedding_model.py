"""Download model files at build time without loading PyTorch into memory."""
import os
from pathlib import Path

from huggingface_hub import snapshot_download


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    snapshot_download(
        repo_id=os.environ.get(
            "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ),
        cache_dir=str(root / ".cache" / "models"),
        allow_patterns=["*.json", "*.txt", "*.model", "*.safetensors"],
    )
    print("Embedding model files cached for deployment.")
