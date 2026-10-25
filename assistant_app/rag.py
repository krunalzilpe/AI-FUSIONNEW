"""Document indexing, retrieval, and grounded answers."""
import logging
from django.conf import settings
from django.db import transaction
from .services.embeddings import get_embedder, index_signature
from .services.extraction import extract_pages, split_text
from .services.vectorstore import get_chroma_collection, delete_document_vectors
from .services.queries import understand_query
from .services.generation import (
    _generate_with_google_genai, generate_answer as _answer,
)
logger = logging.getLogger(__name__)


def _embedding_inputs(texts, role):
    if settings.EMBEDDING_MODEL.startswith("intfloat/multilingual-e5-"):
        return [f"{role}: {text}" for text in texts]
    return texts


def _state(document, status, progress, **extra):
    for key, value in dict(status=status, progress=progress, **extra).items():
        setattr(document, key, value)
    document.save(update_fields=["status", "progress", *extra])


def process_document(document):
    from .models import TextChunk
    signature = index_signature()
    if document.processed and document.index_signature == signature:
        return document.chunk_count
    _state(document, "extracting", 10, processed=False, error="")
    try:
        pages = extract_pages(document.file.path, document.file_type)
        rows, seen = [], set()
        for page_number, text in pages:
            for piece in split_text(text, settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP):
                identity = (page_number, piece)
                if identity not in seen:
                    seen.add(identity)
                    rows.append((page_number, piece))
        if not rows:
            raise ValueError("No readable text found. The document may be blank, or OCR could not recognize the scan. Upload a clearer, upright PDF.")
        _state(document, "embedding", 30)
        vectors = get_embedder().encode(_embedding_inputs([r[1] for r in rows], "passage"), normalize_embeddings=True, show_progress_bar=False, batch_size=32).tolist()
        _state(document, "indexing", 75)
        delete_document_vectors(document.id)
        collection = get_chroma_collection()
        for start in range(0, len(rows), 128):
            stop = min(start + 128, len(rows))
            collection.upsert(
                ids=[f"doc_{document.id}_chunk_{i}" for i in range(start, stop)],
                embeddings=vectors[start:stop], documents=[rows[i][1] for i in range(start, stop)],
                metadatas=[{"doc_id": document.id, "title": document.title, "file_type": document.file_type,
                            "page_number": rows[i][0], "chunk_index": i, "index_signature": signature} for i in range(start, stop)],
            )
        with transaction.atomic():
            document.chunks.all().delete()
            TextChunk.objects.bulk_create([
                TextChunk(document=document, chunk_index=i, page_number=page, text=text, embedding=vectors[i])
                for i, (page, text) in enumerate(rows)
            ])
            _state(document, "ready", 100, processed=True, page_count=len(pages), chunk_count=len(rows), index_signature=signature)
        return len(rows)
    except Exception as exc:
        logger.warning("Document %s indexing failed (%s)", document.id, type(exc).__name__)
        try:
            delete_document_vectors(document.id)
        except Exception:
            pass
        detail = str(exc) if isinstance(exc, ValueError) else "Indexing failed. Check local model availability and ChromaDB storage, then retry."
        _state(document, "failed", 0, processed=False, error=detail[:400])
        raise


def _normalize_document_scope(documents):
    if documents is None:
        return None
    if not isinstance(documents, (list, tuple, set)):
        return []
    ids = set()
    for value in documents:
        if isinstance(value, bool) or not (isinstance(value, int) or isinstance(value, str) and value.isdecimal()):
            return []
        if not 0 < int(value) <= 9223372036854775807:
            return []
        ids.add(int(value))
    return sorted(ids)


def retrieve(question, documents=None, top_k=None, query_info=None):
    from .models import Document, TextChunk
    if not isinstance(question, str) or not question.strip():
        return []
    doc_ids = _normalize_document_scope(documents)
    if doc_ids == []:
        return []
    try:
        top_k = min(20, int(top_k if top_k is not None else settings.RAG_TOP_K))
    except (TypeError, ValueError):
        return []
    if top_k <= 0:
        return []
    info = query_info or understand_query(question)
    eligible = Document.objects.filter(processed=True, index_signature=index_signature())
    if info.get("page") is not None:
        eligible = eligible.filter(file_type="pdf")
    if doc_ids is not None:
        eligible = eligible.filter(id__in=doc_ids)
    allowed_ids = list(eligible.values_list("id", flat=True))
    if not allowed_ids:
        return []
    collection = get_chroma_collection()
    count = collection.count()
    if count == 0:
        return []
    scope = {"doc_id": {"$eq": allowed_ids[0]}} if len(allowed_ids) == 1 else {"doc_id": {"$in": allowed_ids}}
    if info.get("page") is not None:
        scope = {"$and": [scope, {"page_number": {"$eq": info["page"]}}]}
    variants = info.get("variants", [question])[:3]
    vectors = get_embedder().encode(_embedding_inputs(variants, "query"), normalize_embeddings=True, show_progress_bar=False).tolist()
    response = collection.query(query_embeddings=vectors, n_results=min(top_k, count), where=scope, include=["documents", "metadatas", "distances"])
    chunks = TextChunk.objects.filter(document_id__in=allowed_ids).select_related("document").defer("embedding")
    if info.get("page") is not None:
        chunks = chunks.filter(page_number=info["page"])
    metadata_rows = response.get("metadatas") or []
    requested = {meta["chunk_index"] for row in metadata_rows for meta in row if meta and isinstance(meta.get("chunk_index"), int)}
    mapping = {(c.document_id, c.chunk_index): c for c in chunks.filter(chunk_index__in=requested)}
    best = {}
    for row, metadatas in enumerate(metadata_rows):
        for i, meta in enumerate(metadatas):
            if not meta:
                continue
            key = (meta.get("doc_id"), meta.get("chunk_index"))
            chunk = mapping.get(key)
            if not chunk or chunk.text != response["documents"][row][i]:
                continue
            score = max(-1.0, min(1.0, 1.0 - float(response["distances"][row][i])))
            if key not in best or score > best[key]["score"]:
                best[key] = {"chunk": chunk, "score": score, "kind": "semantic"}
    ranked = sorted(best.values(), key=lambda r: r["score"], reverse=True)[:top_k]
    if info.get("summary") or info.get("page") is not None:
        # Broad overviews need coverage beyond nearest neighbours. No fabricated scores.
        ids = list(chunks.order_by("document_id", "chunk_index").values_list("id", flat=True))
        limit = 12
        sampled_ids = ids if len(ids) <= limit else [ids[round(i * (len(ids) - 1) / (limit - 1))] for i in range(limit)]
        by_id = {c.id: c for c in chunks.filter(id__in=sampled_ids)}
        selected = [by_id[id] for id in sampled_ids]
        return [{"chunk": chunk, "score": None, "kind": "coverage"} for chunk in selected]
    return ranked


def generate_answer(question, results, query_info=None):
    return _answer(question, results, query_info, generator=_generate_with_google_genai)


def generate_suggested_questions(document):
    return ["Summarize the main ideas of this document.", "What requirements are listed?", "What are the key findings?"]
