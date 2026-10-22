"""Real integration checks in an isolated test database, never the user's library.

python test_rag_pipeline.py          # Real local embeddings and ChromaDB
python test_rag_pipeline.py --gemini # Also makes real Gemini API calls
"""
import os
import sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "documind.settings")
os.environ["DOCUMIND_INTEGRATION"] = "1"
if "--gemini" in sys.argv:
    os.environ["DOCUMIND_LIVE_GEMINI"] = "1"
import django
django.setup()
from django.test.runner import DiscoverRunner

if __name__ == "__main__":
    failures = DiscoverRunner(verbosity=2).run_tests(["assistant_app.tests_integration"])
    sys.exit(bool(failures))
