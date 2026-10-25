"""Start the local model and Folio together, without cloud API calls."""
import argparse
import json
import os
import secrets
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "local-llm"


def ready():
    try:
        key_file = CACHE / "api-key"
        headers = {"Authorization": "Bearer " + key_file.read_text(encoding="utf8").strip()} if key_file.exists() else {}
        with urlopen(Request("http://127.0.0.1:8081/v1/models", headers=headers), timeout=2) as response:
            return any(item.get("id") == "folio-local" for item in json.load(response).get("data", []))
    except (URLError, ValueError, OSError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()
    binaries = list((CACHE / "runtime").rglob("llama-server.exe"))
    model = CACHE / "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
    if not binaries or not model.exists():
        raise SystemExit("Run python scripts/setup_local_llm.py first (one-time download).")
    key_file = CACHE / "api-key"
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(48), encoding="utf8")
    model_process = None
    app_process = None
    log = None
    try:
        if not ready():
            log = (CACHE / "server.log").open("a", encoding="utf8")
            model_process = subprocess.Popen([
                str(binaries[0]), "--model", str(model), "--alias", "folio-local",
                "--host", "127.0.0.1", "--port", "8081", "--ctx-size", "8192",
                "--threads", str(min(8, os.cpu_count() or 4)), "--parallel", "1",
                "--n-predict", "1024", "--jinja",
                "--api-key-file", str(key_file), "--cors-origins", "localhost", "--no-cors-credentials",
            ], cwd=ROOT, stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            print("Loading the local model...", flush=True)
            deadline = time.monotonic() + 90
            while not ready():
                if model_process.poll() is not None or time.monotonic() >= deadline:
                    raise SystemExit("The local model did not start. See .cache/local-llm/server.log.")
                time.sleep(0.5)
        environment = os.environ.copy()
        environment.update(LLM_PROVIDER="local", LOCAL_LLM_URL="http://127.0.0.1:8081", LOCAL_LLM_MODEL="folio-local")
        print(f"Folio: http://127.0.0.1:{args.port}/ | Local Qwen model | No API credits", flush=True)
        app_process = subprocess.Popen([
            sys.executable, "-u", "manage.py", "runserver", f"127.0.0.1:{args.port}", "--noreload",
        ], cwd=ROOT, env=environment)
        app_process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for process in (app_process, model_process):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        if log:
            log.close()


if __name__ == "__main__":
    main()
