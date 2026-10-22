import hashlib
import json
import uuid

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import FileResponse, JsonResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import ChatMessage, Conversation, Document
from .rag import _normalize_document_scope, generate_answer, retrieve
from .services.embeddings import index_signature
from .services.generation import gemini_configured
from .services.processing import submit_document
from .services.queries import understand_query
from .services.workspaces import workspace_key

MAX_FILE_SIZE = 15 * 1024 * 1024
ACTIVE_STATUSES = {"queued", "extracting", "embedding", "indexing"}


def error(message, status=400, mode="validation_error"):
    return JsonResponse({"success": False, "error": message, "mode": mode}, status=status)


def json_body(request):
    try:
        body = json.loads(request.body)
    except (ValueError, UnicodeError):
        return None
    return body if isinstance(body, dict) else None


def owned_documents(request):
    return Document.objects.filter(workspace_key=workspace_key(request))


def owned_conversations(request):
    return Conversation.objects.filter(workspace_key=workspace_key(request))


def document_data(doc):
    status = doc.status
    if doc.processed and doc.index_signature != index_signature():
        status = "needs_reindex"
    return {"id": doc.id, "title": doc.title, "file_type": doc.file_type,
            "page_count": doc.page_count if doc.file_type == "pdf" else None,
            "chunk_count": doc.chunk_count, "uploaded_at": doc.uploaded_at.isoformat(),
            "status": status, "progress": doc.progress, "error": doc.error,
            "url": reverse("document_source", args=[doc.id])}


def conversation_data(conversation):
    return {"id": conversation.id, "title": conversation.title,
            "updated_at": conversation.updated_at.isoformat(),
            "documents": list(conversation.documents.values_list("id", flat=True))}


def turn_data(turn):
    try:
        sources = json.loads(turn.sources_json)
    except ValueError:
        sources = []
    # Upgrade only navigation/type fields in pre-upgrade history. Keep every stored
    # passage, filename and PDF page exactly as recorded with its original answer.
    if turn.conversation_id:
        ids = [s.get("doc_id") for s in sources if isinstance(s, dict)]
        documents = {d.id: d for d in Document.objects.filter(id__in=ids, workspace_key=turn.conversation.workspace_key)}
        for source in sources:
            doc = documents.get(source.get("doc_id"))
            if doc:
                source.setdefault("file_type", doc.file_type)
                if doc.file_type == "txt":
                    source["page"] = None
                source.setdefault("url", reverse("document_source", args=[doc.id]) + (f"#page={source['page']}" if doc.file_type == "pdf" and source.get("page") else ""))
            else:
                source["url"] = None
                source["unavailable"] = True
    return {"id": turn.id, "conversation_id": turn.conversation_id, "question": turn.question,
            "answer": turn.answer, "mode": turn.mode, "sources": sources,
            "created_at": turn.created_at.isoformat(), "query_metadata": turn.query_metadata}


@ensure_csrf_cookie
@require_GET
def dashboard(request):
    key = workspace_key(request)
    initial = {
        "documents": [document_data(d) for d in owned_documents(request)],
        "conversations": [conversation_data(c) for c in owned_conversations(request).prefetch_related("documents")[:50]],
        "gemini_configured": gemini_configured(),
        "display_name": request.session.get("display_name", "Guest researcher"),
        "workspace_key": key,
    }
    return render(request, "assistant_app/dashboard.html", {"initial": initial})


@require_POST
def upload_document(request):
    uploaded = request.FILES.get("document")
    if not uploaded:
        return error("Choose a PDF or TXT document.")
    extension = uploaded.name.rsplit(".", 1)[-1].lower()
    if extension not in {"pdf", "txt"}:
        return error("Only PDF and TXT files are supported.")
    if not 0 < uploaded.size <= MAX_FILE_SIZE:
        return error("Choose a non-empty file up to 15 MB.")
    if extension == "pdf" and b"%PDF-" not in uploaded.read(1024):
        return error("This file does not have a valid PDF header.")
    uploaded.seek(0)
    digest = hashlib.sha256()
    for part in uploaded.chunks():
        digest.update(part)
    uploaded.seek(0)
    fingerprint = digest.hexdigest()
    key = workspace_key(request)
    existing = owned_documents(request).filter(content_hash=fingerprint).first()
    if existing:
        return JsonResponse({"success": True, "duplicate": True, "document": document_data(existing)})
    doc = Document(workspace_key=key, title=uploaded.name[:255], file=uploaded, file_type=extension, content_hash=fingerprint)
    try:
        with transaction.atomic():
            doc.save()
    except IntegrityError:
        # A concurrent upload won the same content hash. Remove only our unused file.
        if doc.file.name:
            doc.file.delete(save=False)
        existing = owned_documents(request).get(content_hash=fingerprint)
        return JsonResponse({"success": True, "duplicate": True, "document": document_data(existing)})
    if not submit_document(doc):
        doc.status, doc.error = "failed", "The indexing queue is full. Retry shortly."
        doc.save(update_fields=["status", "error"])
    doc.refresh_from_db()
    return JsonResponse({"success": True, "document": document_data(doc)}, status=202)


@require_GET
def list_documents(request):
    docs = list(owned_documents(request))
    return JsonResponse({"success": True, "documents": [document_data(d) for d in docs],
                         "total_chunks": sum(d.chunk_count for d in docs), "gemini_configured": gemini_configured()})


@require_POST
def reindex_document(request, document_id):
    doc = get_object_or_404(owned_documents(request), pk=document_id)
    if doc.status in ACTIVE_STATUSES:
        return error("This document is already processing.", 409, "processing")
    doc.status, doc.progress, doc.processed, doc.error = "queued", 0, False, ""
    doc.save(update_fields=["status", "progress", "processed", "error"])
    if not submit_document(doc):
        doc.status, doc.error = "failed", "The indexing queue is full. Retry shortly."
        doc.save(update_fields=["status", "error"])
        return error(doc.error, 503, "processing_failure")
    return JsonResponse({"success": True}, status=202)


@require_GET
def document_source(request, document_id):
    doc = get_object_or_404(owned_documents(request), pk=document_id)
    try:
        response = FileResponse(doc.file.open("rb"), content_type="application/pdf" if doc.file_type == "pdf" else "text/plain; charset=utf-8")
    except FileNotFoundError:
        raise Http404("Source file is unavailable.")
    from django.utils.http import content_disposition_header
    response["Content-Disposition"] = content_disposition_header(False, doc.title)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_POST
def delete_document(request, document_id):
    doc = get_object_or_404(owned_documents(request), pk=document_id)
    if doc.status in ACTIVE_STATUSES:
        return error("Wait for processing to finish before deleting this document.", 409, "processing")
    from .services.vectorstore import delete_document_vectors
    try:
        delete_document_vectors(doc.id)
    except Exception:
        return error("Vector cleanup failed. The document was retained; retry deletion.", 503, "retrieval_failure")
    try:
        doc.file.delete(save=False)
    except OSError:
        doc.status, doc.processed, doc.error = "failed", False, "File cleanup failed. Retry deleting this document."
        doc.save(update_fields=["status", "processed", "error"])
        return error(doc.error, 503, "processing_failure")
    doc.delete()
    return JsonResponse({"success": True})


def source_data(results):
    return [{"title": r["chunk"].document.title, "doc_id": r["chunk"].document_id,
             "chunk_id": r["chunk"].id, "vector_id": f"doc_{r['chunk'].document_id}_chunk_{r['chunk'].chunk_index}",
             "file_type": r["chunk"].document.file_type,
             "page": r["chunk"].page_number if r["chunk"].document.file_type == "pdf" else None,
             "chunk_index": r["chunk"].chunk_index + 1, "rank": i + 1,
             "score": round(r["score"], 4) if r.get("score") is not None else None,
             "kind": r.get("kind", "semantic"), "text": r["chunk"].text,
             "url": reverse("document_source", args=[r["chunk"].document_id]) + (f"#page={r['chunk'].page_number}" if r["chunk"].document.file_type == "pdf" else "")}
            for i, r in enumerate(results)]


@require_POST
def ask_question(request):
    body = json_body(request)
    if body is None or not isinstance(body.get("question"), str):
        return error("Send a JSON object containing a question.")
    question = body["question"].strip()
    if not question or len(question) > 2000:
        return error("Enter a question between 1 and 2,000 characters.")
    key = workspace_key(request)
    request_id = body.get("request_id")
    if request_id is not None:
        try:
            request_id = uuid.UUID(str(request_id))
        except ValueError:
            return error("Invalid request ID.")
        prior = ChatMessage.objects.filter(request_id=request_id, conversation__workspace_key=key).first()
        if prior:
            if (prior.question != question
                or "documents" in body and _normalize_document_scope(body["documents"]) != prior.query_metadata.get("documents")
                or body.get("conversation_id") is not None and body["conversation_id"] != prior.conversation_id):
                return error("This request ID was already used for another question or document selection.", 409)
            return JsonResponse({"success": True, **turn_data(prior)})
        if ChatMessage.objects.filter(request_id=request_id).exists():
            return error("Use a new request ID.", 409)
    conversation = None
    conversation_id = body.get("conversation_id")
    if conversation_id is not None:
        if isinstance(conversation_id, bool) or not str(conversation_id).isdecimal():
            return error("Invalid conversation ID.")
        conversation = get_object_or_404(owned_conversations(request), pk=conversation_id)
    selection = body.get("documents", list(conversation.documents.values_list("id", flat=True)) if conversation else None)
    selected = _normalize_document_scope(selection)
    if selected == []:
        return error("Select at least one ready document.")
    docs = owned_documents(request)
    if selected is not None:
        docs = docs.filter(id__in=selected)
        if docs.count() != len(selected):
            return error("One or more selected documents are unavailable.", 404)
    docs = list(docs)
    if not docs:
        return error("Upload and select a document first.")
    if any(not d.processed or d.index_signature != index_signature() for d in docs):
        return error("Selected documents are still processing or need reindexing. Check the library.", 409, "processing")
    selected = sorted(d.id for d in docs)
    previous = conversation.messages.order_by("-created_at", "-id").first() if conversation else None
    # Only use follow-up hints from the same document selection.
    same_scope = previous and previous.query_metadata.get("documents") == selected
    info = understand_query(question, previous.question if same_scope else "", previous.answer if same_scope else "")
    lock = "documind-ask:" + key
    if not cache.add(lock, True, timeout=max(180, settings.GEMINI_TIMEOUT_MS // 1000 + 60)):
        return error("A question is already being processed in this workspace.", 409, "busy")
    try:
        try:
            results = retrieve(question, documents=selected, top_k=settings.RAG_TOP_K, query_info=info)
        except Exception:
            return error("Document retrieval is unavailable. Check the embedding model and vector storage, then retry.", 503, "retrieval_failure")
        answer, sources, mode = generate_answer(question, results, info)
        metadata = {"original": question, "normalized": info["normalized"], "language_hint": info["language_hint"],
                    "documents": selected, "requested_page": info["page"], "summary": info["summary"],
                    "retrieved_count": len(results), "index_signature": index_signature(),
                    "scope_note": f"Based on {len(sources)} retrieved excerpts from {len(docs)} selected document(s)."}
        with transaction.atomic():
            if conversation is None:
                conversation = Conversation.objects.create(workspace_key=key, title=question[:100])
            conversation.documents.set(selected)
            conversation.updated_at = timezone.now()
            conversation.save(update_fields=["updated_at"])
            turn = ChatMessage.objects.create(conversation=conversation, question=question, answer=answer, mode=mode,
                                              sources_json=json.dumps(source_data(sources), ensure_ascii=False),
                                              query_metadata=metadata, request_id=request_id)
        return JsonResponse({"success": True, **turn_data(turn)})
    finally:
        cache.delete(lock)


@require_GET
def conversations(request):
    return JsonResponse({"success": True, "conversations": [conversation_data(c) for c in owned_conversations(request).prefetch_related("documents")[:50]]})


@require_GET
def conversation_detail(request, conversation_id):
    conversation = get_object_or_404(owned_conversations(request), pk=conversation_id)
    turns = [turn_data(t) for t in conversation.messages.select_related("conversation").order_by("created_at", "id")]
    # Explicit role records allow other clients to restore the same ordered dialogue.
    messages = []
    for turn in turns:
        messages.extend([{"role": "user", "content": turn["question"], "created_at": turn["created_at"]},
                         {"role": "assistant", "content": turn["answer"], "sources": turn["sources"], "created_at": turn["created_at"]}])
    return JsonResponse({"success": True, "conversation": conversation_data(conversation), "turns": turns, "messages": messages})


@require_POST
def conversation_action(request, conversation_id, action):
    conversation = get_object_or_404(owned_conversations(request), pk=conversation_id)
    if action == "delete":
        conversation.delete()
    elif action == "clear":
        conversation.messages.all().delete()
    elif action == "rename":
        body = json_body(request)
        title = body.get("title") if body else None
        if not isinstance(title, str) or not title.strip() or len(title) > 100:
            return error("Use a title between 1 and 100 characters.")
        conversation.title = title.strip()
        conversation.save(update_fields=["title", "updated_at"])
    else:
        return error("Unknown conversation action.", 404)
    return JsonResponse({"success": True})


@require_POST
def clear_history(request):
    owned_conversations(request).delete()
    return JsonResponse({"success": True})


@require_POST
def profile(request):
    body = json_body(request)
    name = body.get("display_name") if body else None
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 50:
        return error("Use a display name between 1 and 50 characters.")
    request.session["display_name"] = name.strip()
    return JsonResponse({"success": True, "display_name": name.strip()})


@require_GET
def system_stats(request):
    docs = list(owned_documents(request))
    return JsonResponse({"success": True, "total_documents": len(docs), "total_pages": sum(d.page_count for d in docs if d.file_type == "pdf"),
                         "total_chunks": sum(d.chunk_count for d in docs if d.processed),
                         "total_queries": ChatMessage.objects.filter(conversation__workspace_key=workspace_key(request)).count(),
                         "embedding_model": settings.EMBEDDING_MODEL, "vector_store": "ChromaDB · persistent cosine index",
                         "ai_model": settings.GEMINI_MODEL, "gemini_configured": gemini_configured()})


@require_POST
def document_summary(request, document_id):
    # Use the normal conversation endpoint so summary citations are persisted too.
    doc = get_object_or_404(owned_documents(request), pk=document_id)
    request._body = json.dumps({"question": "Summarize this document, stating the excerpt scope.", "documents": [doc.id]}).encode()
    return ask_question(request)


@require_GET
def document_questions(request, document_id):
    doc = get_object_or_404(owned_documents(request), pk=document_id)
    from .rag import generate_suggested_questions
    return JsonResponse({"success": True, "questions": generate_suggested_questions(doc)})


@require_GET
def health(request):
    return JsonResponse({"status": "ok", "service": "OWN GPT", "gemini_configured": gemini_configured()})
