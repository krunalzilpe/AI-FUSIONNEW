# Deployment

Folio is a full-stack Django application. Static-only hosting cannot run its Python backend or local model.

## Current public demo

A temporary HTTPS preview was verified on 25 October 2026 at:

https://boxing-exhaust-serving-avenue.trycloudflare.com

The application runs behind Cloudflare Tunnel with Waitress, DEBUG disabled, an exact allowed hostname, a trusted HTTPS origin, secure cookies, CSRF checks, CSP script nonces, and request limits. The model endpoint stays bound to loopback.

**This is a temporary public demo, not permanent hosting.** It stops when the laptop, model, app, or tunnel stops; the hostname changes when a new quick tunnel is created. See [Cloudflare's quick-tunnel limits](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

## Hosting without API credits

A server with enough RAM can run Django and the quantized model together. Start llama.cpp on loopback or a private network, set `LLM_PROVIDER=local`, and point `LOCAL_LLM_URL` at it. Local inference removes per-request API credits; server resources still need to be provided.

The existing Render Free Blueprint uses the optional Gemini backend. Its 512 MB memory allowance is unsuitable for this local LLM, and may also be insufficient for the embedding model. No paid upgrade is created automatically. Creating a new Docker Space on Hugging Face currently requires a paid plan; do not describe it as a free deployment option.

## Production configuration

- Set a long random `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, exact `ALLOWED_HOSTS`, and HTTPS `CSRF_TRUSTED_ORIGINS`.
- Use a trusted HTTPS reverse proxy. Set `FOLIO_HTTPS_PROXY=true` only when the app is bound behind that proxy; never expose an untrusted forwarded-protocol header directly.
- Run `python manage.py migrate` and `python manage.py collectstatic --noinput`.
- On Linux, use the Gunicorn startup script. On Windows, `python scripts/serve.py --port 8004` uses Waitress on loopback.
- Keep the model service private. Expose the Django application, not the inference port.
- Back up SQLite, uploaded files, and ChromaDB together on persistent storage.
- Original files must use ownership-checked `/document/<id>/source/` endpoints. Never add a public media alias.
- Keep the app's single-worker setting unless background jobs and request-limit storage have been moved to shared services.

`manage.py check --deploy` has two deliberate HSTS advisory warnings: subdomains and browser preload are not enabled for an unowned temporary hostname. HTTPS redirection and HSTS for the current hostname are enabled. Configure those broader HSTS options only for a domain you control.

Anonymous public demos still need operational monitoring, storage quotas, and abuse controls before broader use. A temporary tunnel is not a production uptime promise.
