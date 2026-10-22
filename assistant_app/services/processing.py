from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from django.conf import settings
from django.db import close_old_connections

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="documind-index")
_slots = BoundedSemaphore(4)


def submit_document(document):
    """Small local-development queue; persistent status is stored in SQLite."""
    from assistant_app.rag import process_document
    if not settings.RAG_ASYNC:
        try:
            process_document(document)
        except Exception:
            pass  # process_document records a safe, specific failure state.
        return True
    if not _slots.acquire(blocking=False):
        return False

    def run():
        close_old_connections()
        try:
            from assistant_app.models import Document
            process_document(Document.objects.get(pk=document.pk))
        except Exception:
            pass  # Failure state was recorded by the ingestion service.
        finally:
            close_old_connections()
            _slots.release()
    try:
        _executor.submit(run)
    except Exception:
        _slots.release()
        raise
    return True
