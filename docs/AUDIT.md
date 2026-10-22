# Audit and implementation notes

Audit date: 22 October 2026. The workspace did not contain a `.git` repository, so Git status/diff was unavailable. A source-only baseline was saved to `.local-backup/source-before-enhancement.zip`; it excludes credentials, the database and private documents.

## Existing working functionality

The original project already used real Sentence Transformer embeddings, a persistent ChromaDB cosine collection, pypdf physical-page extraction, overlapping chunks, document selection, the official Google Gen AI SDK, a citation-number validator and stored question/answer pairs. These were not fake retrieval features.

## Critical findings and resolutions

| Finding | Implemented resolution |
|---|---|
| All visitors shared documents and history; sources were served from public development media routes | Backend ownership filtering for documents, conversations, retrieval, deletion, stats and original files; removed public media routing |
| History rows could not reopen a real conversation | Conversation model, scoped M2M document selection, linked turns, explicit roles, restore/rename/clear/delete endpoints |
| TXT passages were displayed as PDF pages | TXT citation pages are null; UI/export use chunk numbers |
| English-only embedder could not support the requested language claims | Configurable multilingual model, real four-language retrieval evaluation and separate model/config collections |
| Embedding changes could silently mix incompatible spaces | SHA-256 model/chunk/token configuration signature, eligibility checks and reindex controls |
| Default multilingual model truncates at 128 tokens | Explicit supported token limit, versioned with the index |
| Index errors/deletion errors could be swallowed | Safe failure states and visible cleanup errors; failed deletion retains metadata/file for retry |
| Upload processing blocked its request | Bounded local worker queue with persistent stage/progress and polling |
| Repeated uploads regenerated identical vectors | Workspace-scoped SHA-256 duplicate constraint and idempotent ingestion |
| Empty selection could widen to all documents | Empty/malformed selections rejected; views always pass authorized IDs |
| Page/summary/follow-up intents were not handled explicitly | Physical-page filtering, bounded coverage excerpts and fresh follow-up retrieval |
| API error text could expose provider details | Safe technical messages, no raw exception/prompt/credential output; current official SDK only |
| Dark-first neon styling, no practical guest panel | Warm light workspace, dark tokens, system/localStorage preference, guest display name/settings and responsive navigation |
| Example environment contained a credential-like value | Replaced with placeholders. The user's actual `.env` was preserved |
| README overstated certainty, production security and previous test results | Replaced with actual behavior, reproducible verification commands and explicit limits |

## Files changed

- Backend: `assistant_app/models.py`, `views.py`, `rag.py`, `documind/settings.py`, `documind/urls.py`.
- New services: `assistant_app/services/{embeddings,extraction,generation,processing,queries,vectorstore,workspaces}.py`.
- Migrations: `0003_conversation_chatmessage_query_metadata_and_more.py`, `0004_preserve_legacy_status.py`.
- Recovery/indexing commands: `assistant_app/management/commands/{adopt_legacy,reindex_documents}.py`.
- Interface: `templates/assistant_app/dashboard.html`, `static/assistant_app/style.css`, `static/assistant_app/workspace.js`.
- Verification: `assistant_app/tests.py`, `tests_features.py`, `tests_integration.py`, `test_fixtures.py`, `test_rag_pipeline.py`, `scripts/{smoke_http,diagnose_gemini}.py`.
- Configuration/documentation: `.env.example`, `.gitignore`, `requirements.txt`, `README.md`, `docs/`.

The legacy data stays unassigned until the operator explicitly adopts it into a known workspace. This preserves the data without exposing it to an arbitrary new visitor. The original sample file was not overwritten by the new tests.

## Remaining boundaries

Local OCR was added after this audit; see [OCR setup and verification](OCR.md). A durable worker queue, public account onboarding and verified deployment remain outstanding. A cosine threshold and citation-number validation reduce errors but do not prove factual entailment. Browser-level visual/theme/mobile verification depends on a connected browser; see the verification record for what actually ran.
