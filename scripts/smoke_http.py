"""Exercise a running server with synthetic documents in a separate guest session.

python scripts/smoke_http.py --url http://127.0.0.1:8001 --gemini
Only this script's documents and conversations are removed afterwards.
"""
import argparse
import sys
import time
import uuid
from pathlib import Path

import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from assistant_app.test_fixtures import pdf_bytes, scanned_pdf_bytes, KNOWN_PAGES

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8001")
parser.add_argument("--gemini", action="store_true")
parser.add_argument("--ocr", action="store_true", help="Also upload and retrieve a real image-only PDF")
args = parser.parse_args()
base = args.url.rstrip("/")
session = requests.Session()
session.get(base + "/", timeout=10).raise_for_status()
headers = {"X-CSRFToken": session.cookies["csrftoken"]}
owned_ids = []


def post(path, data):
    response = session.post(base + path, json=data, headers=headers, timeout=110)
    response.raise_for_status()
    return response.json()


def wait_ready(doc_id):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        docs = session.get(base + "/documents/", timeout=10).json()["documents"]
        doc = next(doc for doc in docs if doc["id"] == doc_id)
        if doc["status"] == "ready":
            return doc
        if doc["status"] == "failed":
            raise AssertionError(doc["error"])
        time.sleep(1)
    raise AssertionError("Document did not become ready within 180 seconds")


try:
    content = pdf_bytes(KNOWN_PAGES)
    upload = session.post(base + "/upload/", files={"document":("smoke_known_facts.pdf", content, "application/pdf")}, headers=headers, timeout=30)
    upload.raise_for_status()
    doc_id = upload.json()["document"]["id"]; owned_ids.append(doc_id)
    assert upload.status_code == 202
    doc = wait_ready(doc_id)
    assert doc["page_count"] == 3
    print("PASS real asynchronous PDF upload, extraction, embeddings and indexing")
    duplicate = session.post(base + "/upload/", files={"document":("duplicate.pdf", content, "application/pdf")}, headers=headers, timeout=30).json()
    assert duplicate["duplicate"] and duplicate["document"]["id"] == doc_id
    print("PASS content-hash duplicate detection")
    txt = session.post(base + "/upload/", files={"document":("smoke_notes.txt", b"The release code is AURORA-42.", "text/plain")}, headers=headers, timeout=30)
    txt.raise_for_status()
    txt_id = txt.json()["document"]["id"]; owned_ids.append(txt_id); wait_ready(txt_id)
    print("PASS real asynchronous TXT upload")
    request_id = str(uuid.uuid4())
    request = {"question":"What is the project budget?", "documents":[doc_id], "request_id":request_id}
    answer = post("/ask/", request)
    assert not args.gemini or answer["mode"] == "gemini", answer["answer"]
    assert answer["mode"] in {"gemini","retrieval_only"}, answer["answer"]
    assert any(source["page"] == 2 and "750000" in source["text"] for source in answer["sources"])
    assert all(source["doc_id"] == doc_id for source in answer["sources"])
    repeated = post("/ask/", request)
    assert repeated["id"] == answer["id"]
    print(f"PASS {answer['mode']} response, page-2 source passage, document scope and idempotency")
    conversation_id = answer["conversation_id"]
    history = session.get(base + f"/conversation/{conversation_id}/", timeout=10).json()
    assert history["turns"][0]["sources"] == answer["sources"]
    assert [m["role"] for m in history["messages"]] == ["user","assistant"]
    print("PASS history restoration with unchanged citations")
    source = session.get(base + answer["sources"][0]["url"], timeout=10)
    assert source.status_code == 200 and source.content == content
    other = requests.Session(); other.get(base + "/", timeout=10)
    assert other.get(base + f"/document/{doc_id}/source/", timeout=10).status_code == 404
    assert other.get(base + f"/conversation/{conversation_id}/", timeout=10).status_code == 404
    print("PASS protected source delivery and cross-session isolation")
    unsupported = post("/ask/", {"question":"Who won the 2022 football world cup?", "documents":[doc_id], "conversation_id":conversation_id})
    assert unsupported["mode"] == "no_evidence", unsupported["answer"]
    assert unsupported["sources"] == []
    print("PASS unsupported question returns insufficient evidence without invented citations")
    if args.ocr:
        scanned = scanned_pdf_bytes(["Aurora Flood Monitoring Project\nSensors measure river levels.", "Project Administration\nThe project budget is 750000 rupees.\nThe coordinator is Anika Rao."])
        upload = session.post(base + "/upload/", files={"document":("smoke_scan.pdf", scanned, "application/pdf")}, headers=headers, timeout=30)
        upload.raise_for_status()
        scan_id = upload.json()["document"]["id"]; owned_ids.append(scan_id)
        assert wait_ready(scan_id)["page_count"] == 2
        answer = post("/ask/", {"question":"What is the project budget?", "documents":[scan_id]})
        assert any(s["page"] == 2 and s["title"] == "smoke_scan.pdf" and "750000" in s["text"] for s in answer["sources"])
        assert all(s["doc_id"] == scan_id for s in answer["sources"])
        assert session.get(base + f"/document/{scan_id}/source/", timeout=10).content == scanned
        print("PASS real scanned PDF upload, local OCR, embeddings, retrieval and original page-2 citation")
    print("HTTP SMOKE PASSED")
finally:
    for doc_id in owned_ids:
        post(f"/document/{doc_id}/delete/", {})
    post("/history/clear/", {})
    assert session.get(base + "/documents/", timeout=10).json()["documents"] == []
    print("PASS cleanup: this smoke session's documents, files, vectors and history removed")
