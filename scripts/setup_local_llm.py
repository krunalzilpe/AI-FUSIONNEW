"""Download Folio's optional local model and portable Windows runtime."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from threading import Lock
import time
import urllib.request
import zipfile
import zlib

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "local-llm"
MODEL_NAME = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
MODEL_URL = "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/" + MODEL_NAME
MODEL_SHA256 = "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597"
BUILD = "b11669"
RUNTIME_NAME = f"llama-{BUILD}-bin-win-cpu-x64.zip"
RUNTIME_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{BUILD}/{RUNTIME_NAME}"
RUNTIME_SHA256 = "37b3efcf962847ca869745fd4ccf7f5e7e8dacfeff9fa3523b4ca8cdc66d632b"


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def download_ranges(url, temporary, size, checksum):
    """Resume large downloads using disjoint ranges, then verify the whole file."""
    checkpoint = temporary.with_suffix(".progress.json")
    state = None
    if temporary.exists() and checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="utf8"))
        if saved.get("sha256") == checksum and saved.get("size") == size:
            state = saved
    if state is None:
        prefix = temporary.stat().st_size if temporary.exists() else 0
        state = {"size": size, "sha256": checksum, "prefix": min(prefix, size), "complete": []}
        checkpoint.write_text(json.dumps(state), encoding="utf8")
    with temporary.open("r+b" if temporary.exists() else "wb") as target:
        target.truncate(size)
    block_size = 32 * 1024 * 1024
    ranges = [(start, min(start + block_size, size) - 1) for start in range(state["prefix"], size, block_size)]
    pending = [(start, end) for start, end in ranges if start not in state["complete"]]
    lock = Lock()

    def fetch(bounds):
        start, end = bounds
        for attempt in range(4):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Folio-local-setup/1.0", "Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(request, timeout=60) as response, temporary.open("r+b") as target:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                        raise RuntimeError("The download server did not honor the byte range.")
                    target.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = response.read(min(4 * 1024 * 1024, remaining))
                        if not chunk:
                            raise OSError("Interrupted model download")
                        target.write(chunk)
                        remaining -= len(chunk)
                with lock:
                    state["complete"].append(start)
                    checkpoint.write_text(json.dumps(state), encoding="utf8")
                    downloaded = state["prefix"] + sum(end - begin + 1 for begin, end in ranges if begin in state["complete"])
                    print(f"  {downloaded // (1024 * 1024)} MB / {size // (1024 * 1024)} MB", flush=True)
                return
            except (OSError, RuntimeError):
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(fetch, pending))
    return checkpoint


def download(url, destination, checksum):
    if destination.exists() and digest(destination) == checksum:
        print(f"Already verified: {destination.name}", flush=True)
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "Folio-local-setup/1.0"})
    print(f"Downloading {destination.name}...", flush=True)
    response = urllib.request.urlopen(request, timeout=60)
    size = int(response.headers.get("Content-Length", 0))
    if size > 256 * 1024 * 1024:
        response.close()
        checkpoint = download_ranges(url, temporary, size, checksum)
        if digest(temporary) != checksum:
            raise RuntimeError(f"Checksum mismatch for {destination.name}; remove its .part file and rerun setup.")
        temporary.replace(destination)
        checkpoint.unlink(missing_ok=True)
        return
    with response, temporary.open("wb") as target:
        size = int(response.headers.get("Content-Length", 0))
        received, reported = 0, -1
        while block := response.read(4 * 1024 * 1024):
            target.write(block)
            received += len(block)
            progress = received * 10 // size if size else received // (100 * 1024 * 1024)
            if progress > reported:
                print(f"  {received // (1024 * 1024)} MB" + (f" / {size // (1024 * 1024)} MB" if size else ""), flush=True)
                reported = progress
    if digest(temporary) != checksum:
        raise RuntimeError(f"Checksum mismatch for {destination.name}; rerun setup.")
    temporary.replace(destination)


def main():
    if sys.platform != "win32":
        raise SystemExit("Use llama.cpp for your OS, then set LOCAL_LLM_URL. See docs/LOCAL_LLM.md.")
    CACHE.mkdir(parents=True, exist_ok=True)
    download(RUNTIME_URL, CACHE / RUNTIME_NAME, RUNTIME_SHA256)
    runtime = CACHE / "runtime"
    runtime.mkdir(exist_ok=True)
    with zipfile.ZipFile(CACHE / RUNTIME_NAME) as archive:
        for entry in archive.infolist():
            target = runtime / entry.filename
            if not target.resolve().is_relative_to(runtime.resolve()):
                raise RuntimeError("Unsafe archive path")
            if target.is_file() and zlib.crc32(target.read_bytes()) == entry.CRC:
                continue
            archive.extract(entry, runtime)
    download(MODEL_URL, CACHE / MODEL_NAME, MODEL_SHA256)
    (CACHE / "model.json").write_text(json.dumps({"model": MODEL_NAME, "sha256": MODEL_SHA256, "runtime": BUILD}, indent=2), encoding="utf8")
    print("Ready. Start Folio with: python scripts/run_local.py", flush=True)


if __name__ == "__main__":
    main()
