# DocuMind AI

Your documents, understood. A Django document workspace for questions in English, Hindi, Roman Hinglish and Marathi, with original source passages beneath each answer.

Built for the AI-FUSION Webathon using **Python, Django templates, Bootstrap 5, vanilla JavaScript, SQLite, Sentence Transformers, ChromaDB, pypdf and the official Google Gen AI SDK**. This enhancement preserves the existing Django project and its public RAG entry points.

## What works

- PDF/TXT uploads up to 15 MB, content-hash deduplication within each workspace, UTF-8 validation, malformed/empty-PDF handling and local OCR for scanned pages (English/Hindi/Marathi models).
- Background processing with persisted extraction, embedding and indexing states. The first model download can take several minutes.
- Real normalized dense embeddings and persistent ChromaDB cosine search. Each embedding/chunking configuration has a separate collection; incompatible indexes are never mixed.
- Real PDF physical page numbers, TXT chunk numbers, complete original retrieved passages, genuine cosine scores or explicitly labelled coverage samples.
- Source previews and ownership-checked original files. PDF links include `#page=N`; navigation depends on the browser's PDF viewer.
- Gemini receives selected retrieved excerpts. Invalid/missing citations are rejected. Insufficient evidence, processing failures, retrieval failures, missing credentials and API failures have separate outcomes.
- Conservative language/page/summary hints and fresh retrieval for follow-up questions. The original user question is always preserved.
- Saved conversations with titles, rename, reopen, clear, delete, ordered user/assistant roles, timestamps and source snapshots tied to their original answers.
- Personal guest-session document libraries and history. Authenticated Django users also receive a distinct server-side ownership scope; this app does not add public registration/login screens.
- A light-first workspace with a system-aware dark theme, persistent appearance preference, mobile navigation, document filtering, source cards, copy/export and duplicate-submission protection.

There is no guarantee of error-free AI answers. Retrieval similarity is not a calibrated confidence score, and citation-number validation cannot prove every generated claim follows from its source. Read the passages when accuracy matters.

## Windows setup

Use **Python 3.12** for the tested dependency stack. Run these commands from the project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If `.venv` and `.env` already exist, preserve them. With uv, installation can instead use `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`.

Edit `.env` and set `GEMINI_API_KEY`. `GEMINI_MODEL` must be a model available to that key. The example defaults to `gemini-flash-latest`; an existing configured model is respected. No deprecated Gemini SDK is used. `GEMINI_TIMEOUT_MS` bounds individual API requests; transient HTTP errors receive at most one retry, so a complete operation can take roughly twice that timeout.

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001
```

Open **http://127.0.0.1:8001/**. Port 8001 avoids conflicting with an older development instance on port 8000. `DJANGO_DEBUG` is the explicit development/production switch; it takes precedence over legacy `DEBUG`. The IDE's `DEBUG=release` mode is not treated as a Django boolean.

On first upload, the multilingual model downloads into `.cache/models/`. Complete cached snapshots are loaded locally on subsequent starts. Embeddings remain local; retrieved excerpts are sent to Gemini only when generating an answer. Without a key, the app shows original retrieved passages and clearly identifies generation as unavailable.

For scanned PDFs, run `.venv\Scripts\python.exe scripts/setup_ocr.py` once after installing dependencies, then restart Django. See [OCR setup](docs/OCR.md).

## Existing documents and embedding changes

Pre-upgrade files and answers are **preserved**, with no automatic assignment to the first browser visitor. This prevents the old global library from leaking into a new guest session.

1. Open Settings and copy its **Local recovery ID**.
2. Assign the pre-upgrade library to that workspace using the local administrative command:

```powershell
.\.venv\Scripts\python.exe manage.py adopt_legacy --workspace-key "guest:PASTE-THE-ID-FROM-SETTINGS"
.\.venv\Scripts\python.exe manage.py reindex_documents --all
```

Do not paste the illustrative placeholder literally. The recovery ID identifies a local workspace; it is not a login credential. The command requires local access to the project/database and should be run only by its operator.

Changing `EMBEDDING_MODEL`, `EMBEDDING_MAX_TOKENS` or chunk settings requires reindexing. Existing documents show **Reindex required** until rebuilt. Use **Retry indexing** in the library or `reindex_documents --document 1`. Stop other ingestion jobs before running a bulk recovery. The same command recovers jobs interrupted by a server restart.

Guest identity is tied to the Django session cookie (two weeks by default). Clearing cookies or changing browsers loses access to that guest identity. It is not a persistent cross-device account.

## Architecture

```text
Upload → validate + hash → page-aware extraction → overlapping chunks
       → one cached multilingual embedder → versioned persistent ChromaDB index
Question + authorized scope → conservative intent hints → query embeddings
       → filtered semantic retrieval → evidence gate → Gemini with source context
       → answer + original passages → scoped conversation/source snapshots
```

`assistant_app/rag.py` orchestrates the pipeline. `services/` separates extraction, model loading, vector persistence, query handling, generation, processing and ownership. SQLite is authoritative for citation metadata; stale or orphaned vectors are discarded. Summaries sample up to 12 excerpts across the selected scope and disclose that coverage.

The multilingual MiniLM encoder defaults to 128 tokens. This project configures its supported 512-token limit to avoid silently truncating ordinary chunks; that setting is included in the index signature.

## Verification commands

```powershell
# Fast regression tests; no live API calls or model downloads
.\.venv\Scripts\python.exe manage.py test assistant_app.tests assistant_app.tests_features

# Real embeddings, ChromaDB, physical PDF pages and four-language retrieval
.\.venv\Scripts\python.exe -X utf8 test_rag_pipeline.py

# Also calls Gemini with synthetic fixtures, including response-language checks
.\.venv\Scripts\python.exe -X utf8 test_rag_pipeline.py --gemini

# Exercise a running server, including actual background processing and CSRF
.\.venv\Scripts\python.exe scripts\smoke_http.py --url http://127.0.0.1:8001 --gemini

# A small API availability diagnostic; never prints credentials
.\.venv\Scripts\python.exe scripts\diagnose_gemini.py

node --check static\assistant_app\workspace.js
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

The integration runner creates a separate test database and temporary media/vector storage. It does not delete or replace the user's sample document. The HTTP smoke test uses its own guest session and removes only its synthetic fixtures. Node is optional for JavaScript syntax checking; it is not part of the app's runtime.

See [verification results](docs/VERIFICATION.md), [audit and changed files](docs/AUDIT.md), [deployment](docs/DEPLOYMENT.md), and the [demo and Q&A](docs/DEMO.md).

## Practical limits

Local OCR supports clear printed scans; see [OCR setup and limits](docs/OCR.md). Handwriting and poor scans are not guaranteed. Summaries of long documents use bounded samples. The small local thread queue is not a durable production job system; interrupted jobs need a retry. Language hints are heuristics, not a full language classifier, and the small labelled retrieval fixture is not a broad multilingual benchmark. Bootstrap and optional web fonts load from CDNs; system fonts and the core custom styles remain available without fonts.

No live deployment has been created or verified. Do not serve private files directly from `/media/`; the application uses its protected source endpoint instead. The workspace is suitable for a local demonstration; production needs the deployment controls described in the deployment guide.
