"""Check configured Gemini availability without printing credentials or private content."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "documind.settings")
import django
django.setup()
from django.conf import settings
from assistant_app.services.generation import _generate_with_google_genai, gemini_configured

if not gemini_configured():
    print("Gemini API key is not configured.")
    sys.exit(1)
try:
    answer = _generate_with_google_genai("Return only the word OK.", [settings.GEMINI_MODEL], os.environ["GEMINI_API_KEY"])
    print("Gemini model:", settings.GEMINI_MODEL)
    print("API response received:", bool(answer.strip()))
except Exception as exc:
    print("Gemini request failed:", type(exc).__name__)
    print("HTTP/provider code:", getattr(exc, "code", "unavailable"))
    sys.exit(1)
