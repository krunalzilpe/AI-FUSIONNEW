from functools import lru_cache

from django.conf import settings
from .embeddings import index_signature


@lru_cache(maxsize=4)
def _client(path):
    import chromadb
    return chromadb.PersistentClient(path=path)


def collection_name():
    return "documind_" + index_signature()[:20]


def get_chroma_collection():
    return _client(str(settings.CHROMA_DB_PATH)).get_or_create_collection(
        name=collection_name(), metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )


def delete_document_vectors(document_id):
    """Clean all model versions, including the pre-upgrade collection. Fail visibly."""
    client = _client(str(settings.CHROMA_DB_PATH))
    for collection in client.list_collections():
        name = collection if isinstance(collection, str) else collection.name
        if name.startswith("documind_"):
            client.get_collection(name, embedding_function=None).delete(where={"doc_id": int(document_id)})
