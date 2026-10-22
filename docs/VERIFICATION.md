# Final audit — 22 October 2026

Scope: verify the existing implementation, preserve all changes, and avoid new features/redesigns. The only final-audit code edit corrected a misleading smoke-test log label: a retrieval-only response is now labelled `retrieval_only`, not a generated answer.

## Executed results

| Status | Check | Evidence / smallest action |
|---|---|---|
| PASS | Django checks, imports, templates, startup | `manage.py check` found no issues; current server started on 127.0.0.1:8001; dashboard/static endpoints returned HTTP 200. |
| PASS | Migrations | All four assistant_app migrations applied; `makemigrations --check --dry-run` reported no changes. |
| PASS | Dependencies | `uv pip check --python .venv/Scripts/python.exe` checked 122 packages; all compatible. |
| PASS | Regression tests | 46 tests passed in the final run. Covers ownership, CSRF, uploads, malformed inputs, citation preservation, TXT references, history, deletion failures, idempotency, model mismatch and safe API errors. |
| PASS | Actual local RAG | 7 real integration tests passed; 2 live-generation tests explicitly skipped in this final local run. Actual model embeddings, persistent Chroma text/vector/page metadata, semantic query, document filtering, page selection, coverage sampling, vector cleanup and model reuse were tested. |
| PASS | Multilingual retrieval | English, Hinglish, Hindi and Marathi questions all ranked the correct budget passage on physical PDF page 2. Cosines: 0.7056 / 0.6797 / 0.6997 / 0.6178. Warm retrieval measured 24–38 ms for these small fixtures. This is a sample evaluation, not a broad benchmark. |
| PASS | Grounding path | Source inspection and passing prompt tests confirm retrieval runs before generation and actual numbered retrieved passages are included in Gemini's context. |
| PASS | Source integrity | Known PDF facts on different physical pages, a blank PDF page, original filenames, actual passage text, source IDs, history association and null TXT page numbers tested. Source endpoint returns the original PDF bytes after ownership checks. |
| PASS | Missing key / API failures | Missing credentials return clearly labelled original passages; provider exceptions and 429 errors remain `provider_error` with original evidence, never fabricated answers or false `no_evidence`. |
| PASS | Actual HTTP workflow | A separate guest session uploaded PDF/TXT through the running server, waited for real background indexing, verified duplicates, retrieved the page-2 budget source, restored history, checked protected source delivery/session isolation, tested an absent answer and cleaned up its own documents/history. This final smoke used an explicit placeholder API key and therefore tested retrieval-only mode, not live generation. |
| PASS | JavaScript/static UI structure | `node --check` passed. Rendered HTML has no duplicate IDs and no missing literal JavaScript target IDs. Theme tokens, early preference restoration, localStorage persistence, mobile rules, source cards, loading/error logic and reduced-motion rules inspected. |
| FAIL | Reliable live Gemini availability | An earlier live test succeeded for a grounded English answer and an unsupported question. Subsequent runs intermittently returned 503/504, then 429. Hinglish/Hindi/Marathi generation each succeeded in individual runs, but the final live suite was not consistently green. Component: configured Gemini provider / `assistant_app/services/generation.py`. Smallest action: restore quota/rate availability and use a model available to the key, then rerun `test_rag_pipeline.py --gemini`. Do not rewrite the RAG pipeline. |
| NOT TESTED | Browser interactions and visual layout | Browser inventory was empty. Actual light/dark switching, persistence after browser refresh, mobile layout, button clicks, clipboard/export and native PDF viewer page navigation were not visually verified. Static review is not a substitute for browser testing. |
| NOT TESTED | Live deployment | No deployment was created or verified. Development security warnings are not a production approval; follow the deployment guide. |

## Commands executed

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py showmigrations assistant_app
uv pip check --python .venv\Scripts\python.exe
.\.venv\Scripts\python.exe manage.py test assistant_app.tests assistant_app.tests_features --verbosity 1
.\.venv\Scripts\python.exe -X utf8 test_rag_pipeline.py
node --check static\assistant_app\workspace.js
.\.venv\Scripts\python.exe scripts\smoke_http.py --url http://127.0.0.1:8002
```

Live checks earlier in the same session used `test_rag_pipeline.py --gemini` and `scripts/diagnose_gemini.py` with authorized network access and synthetic passages. Further API calls were stopped after the quota/rate error.

The test server's explicit placeholder credential was process-local; the user's `.env` was not changed. The normal updated application remains on **http://127.0.0.1:8001/**. An older port-8000 instance was preserved.

## Demo readiness

**Ready for a local retrieval/citation demonstration. Not yet reliable for a live Gemini-powered demonstration.** The remaining confirmed critical blocker is external Gemini service/quota availability. Browser interactions remain an explicit verification gap. No additional application rebuild is recommended.
