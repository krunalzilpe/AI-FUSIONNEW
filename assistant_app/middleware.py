"""Small request limits for the single-worker public demo."""
import hashlib
import secrets
import time

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(24)
        response = self.get_response(request)
        response["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{request.csp_nonce}'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; "
            "form-action 'self'; frame-ancestors 'none'"
        )
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


class RequestLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.RATE_LIMIT_ENABLED and request.method == "POST" and request.path in {"/ask/", "/upload/"}:
            minute = int(time.time() // 60)
            address = request.META.get("REMOTE_ADDR", "unknown")
            identity = hashlib.sha256(address.encode()).hexdigest()[:24]
            key = f"folio-rate:{identity}:{request.path}:{minute}"
            cache.add(key, 0, timeout=120)
            try:
                count = cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=120)
                count = 1
            limit = settings.CHAT_REQUESTS_PER_MINUTE if request.path == "/ask/" else settings.UPLOADS_PER_MINUTE
            if count > limit:
                response = JsonResponse({"success": False, "mode": "busy", "error": "Too many requests. Please wait a minute before trying again."}, status=429)
                response["Retry-After"] = "60"
                return response
        return self.get_response(request)
