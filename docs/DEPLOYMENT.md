# Deployment

Folio is a full-stack Django application. Static-only hosting cannot run its Python backend or local model.

## Public demo

The existing Render service is at https://documind-ai-fusionnew-1gbe.onrender.com/ and deploys from `krunalzilpe/AI-FUSIONNEW`, branch `main`.

Render Free can sleep when idle. Uploaded files, SQLite history, and indexes use its temporary filesystem and can reset on restarts or deploys. Use persistent storage for durable accounts or documents.

## Hosting without API credits

A server with enough RAM can run Django and the quantized model together. Start llama.cpp on loopback or a private network, set `LLM_PROVIDER=local`, and point `LOCAL_LLM_URL` at it. Local inference removes per-request API credits; server resources still need to be provided.

The Render Free Blueprint uses hosted Gemma 4 with the existing server-side Google API key. Google currently lists Gemma 4 input/output as free of charge, with rate limits; see [official pricing](https://ai.google.dev/gemini-api/docs/pricing#gemma-4). The 512 MB allowance is unsuitable for the local Qwen LLM. No paid upgrade is created automatically.

Document embeddings stay local: Render selects `EMBEDDING_BACKEND=onnx`, a pinned INT8 export of multilingual E5 small. It runs through ONNX Runtime without loading PyTorch and limits inference to two passages at a time. Docker caches the tokenizer and weights at build time; uploads need no model download. `EMBEDDING_BACKEND=pytorch` remains available on larger local machines. Each backend uses a separate index signature; changing it requires reindexing documents.

## Production configuration

- Set a long random `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, exact `ALLOWED_HOSTS`, and HTTPS `CSRF_TRUSTED_ORIGINS`.
- The container startup preserves a valid configured signing key. If none is valid, it generates a private key in `.cache/django-secret.key` and captures it without printing it. Set `DJANGO_SECRET_KEY_FILE` to a persistent private path for durable storage; Render Free resets local files on instance replacement.
- Use a trusted HTTPS reverse proxy. Set `FOLIO_HTTPS_PROXY=true` only when the app is bound behind that proxy; never expose an untrusted forwarded-protocol header directly.
- Run `python manage.py migrate` and `python manage.py collectstatic --noinput`.
- On Linux, use the Gunicorn startup script. On Windows, `python scripts/serve.py --port 8004` uses Waitress on loopback.
- Keep the model service private. Expose the Django application, not the inference port.
- Back up SQLite, uploaded files, and ChromaDB together on persistent storage.
- Original files must use ownership-checked `/document/<id>/source/` endpoints. Never add a public media alias.
- Keep the app's single-worker setting unless background jobs and request-limit storage have been moved to shared services.

`manage.py check --deploy` has two deliberate HSTS advisory warnings: subdomains and browser preload are not enabled for an unowned temporary hostname. HTTPS redirection and HSTS for the current hostname are enabled. Configure those broader HSTS options only for a domain you control.

Anonymous public demos still need operational monitoring, storage quotas, and abuse controls before broader use. A temporary tunnel is not a production uptime promise.
