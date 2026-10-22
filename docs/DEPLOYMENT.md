# Deployment guide

Deployment status: **not deployed**. No hosting URL has been created or verified.

## Local demonstration

Use the Windows commands in the README. Keep `DJANGO_DEBUG=True`, bind the development server to `127.0.0.1`, and open the chosen local port. Run the real integration and HTTP smoke tests before the demo. Download the embedding model before judging starts so a cold download does not interrupt the upload.

## A small hosted installation

The simplest arrangement is one Django application instance with a persistent disk for SQLite, media files, ChromaDB and the model cache. Ephemeral filesystems lose the document/index state on restart. This implementation's local queue is intended for a small demonstration, not a multi-worker production ingestion service.

1. Install Python 3.12 and `requirements.txt` in an isolated environment.
2. Configure a long random `DJANGO_SECRET_KEY`, `GEMINI_API_KEY`, a valid `GEMINI_MODEL`, `DJANGO_DEBUG=False`, and explicit `ALLOWED_HOSTS`.
3. Use HTTPS. Secure session/CSRF cookies are enabled outside debug mode. Configure trusted origins and reverse-proxy HTTPS headers for your actual host; do not blindly trust arbitrary forwarded headers.
4. Run migrations and `python manage.py collectstatic --noinput`. Use a suitable production WSGI/ASGI server and a reverse proxy rather than Django's development server. For example, install Gunicorn separately on a Linux host and run `gunicorn documind.wsgi:application --workers 1 --bind 127.0.0.1:8000 --timeout 120`.
5. Serve `/static/` from `static_collected/`. Do **not** add a public `/media/` alias. Original documents must pass through `/document/<id>/source/`, which checks workspace ownership.
6. Keep SQLite, files and ChromaDB together in a backup plan. Limit upload/body sizes at the reverse proxy. Use appropriate file/disk quotas for the hosting environment.
7. Run `python manage.py check --deploy`, then address its findings for the chosen HTTPS/proxy configuration. Verify source authorization, sessions, upload and generation through the public host before declaring deployment complete.

Before serving a broader multi-user audience, implement durable ingestion jobs, rate limits, storage quotas and deliberate account/session lifecycle controls. The in-process request lock and queue do not coordinate multiple Django worker processes. No claim of production-grade multi-user security is made.

## Recovery and model changes

Back up SQLite and files before changing an embedding configuration. Rebuild with `python manage.py reindex_documents --all`; the versioned collection prevents a new query model from searching incompatible old vectors. Stop concurrent ingestion while running a bulk rebuild. Jobs interrupted by a restart can be retried from the library or through that command.

Pre-upgrade global data can be assigned using `adopt_legacy --workspace-key` with a specific Settings recovery ID. Keep administrative project/database access private.
