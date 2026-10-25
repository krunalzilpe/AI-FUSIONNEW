"""Serve Folio on loopback with Waitress, behind a configured HTTPS proxy."""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "documind.settings")

from django.core.wsgi import get_wsgi_application
from waitress import serve


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8004)
    args = parser.parse_args()
    serve(get_wsgi_application(), host="127.0.0.1", port=args.port,
          threads=4, channel_timeout=240, max_request_body_size=16 * 1024 * 1024,
          ident="", trusted_proxy="127.0.0.1", trusted_proxy_headers="x-forwarded-proto")
