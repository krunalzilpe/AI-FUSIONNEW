# Four-to-five-minute demonstration

Use a text-based PDF with known facts on different physical pages. Avoid private documents. The integration fixture in `assistant_app/test_fixtures.py` defines a three-page Aurora flood-monitoring example.

| Time | Demonstration |
|---|---|
| 0:00–0:35 | Explain the problem: finding trustworthy information in long documents. Show the personal workspace and say that answers are tied to retrieved source passages. |
| 0:35–1:15 | Upload PDF and TXT. Show real processing states and the ready chunk count. Explain that PDFs preserve physical page numbers and TXT uses chunk numbers. |
| 1:15–2:05 | Ask a known factual question. Expand the source card, show the actual original passage and correct page, preview it, then open the original PDF. |
| 2:05–2:50 | Ask the budget question in Hinglish, Hindi or Marathi. Point out that the answer follows the user's language while the source passage remains in its original language. |
| 2:50–3:25 | Ask about a specific page and then request a summary. Explain the bounded excerpt scope for long summaries. |
| 3:25–4:00 | Ask a clearly unsupported question. Show insufficient evidence and the absence of invented citations. Explain that API failures are a separate technical error. |
| 4:00–4:45 | Reopen the saved conversation to show unchanged citations. Demonstrate document selection and appearance settings. Finish with the real retrieval architecture and its limits. |

Preflight: run the API diagnostic and HTTP smoke test, warm the local embedding model, verify quotas and the selected Gemini model, and use the updated server port. If the provider is unavailable, demonstrate retrieval-only evidence honestly. Do not claim a live deployment or guaranteed zero hallucinations.

# Two-minute Q&A

**Is this real RAG?** Yes. The app extracts PDF/TXT text, creates overlapping chunks, computes local dense embeddings, stores embeddings/text/metadata in persistent ChromaDB, semantically retrieves authorized chunks and sends only those excerpts to Gemini.

**How are citations trustworthy?** Each chunk keeps its document ID, original filename, chunk identity and physical PDF page. SQLite verifies retrieved metadata against stored chunks. The answer's allowed source numbers are checked, and the exact source snapshot is saved with that answer. This validates provenance and numbering; it does not prove every model sentence is correct.

**How does multilingual input work?** One configurable multilingual model embeds documents and queries in the same space. Small intent hints support Hinglish, page references and summaries. The original question reaches Gemini with response-language instructions. Real four-language sample retrieval is tested; the fixture is not a broad language benchmark.

**How is access isolated?** Every view scopes metadata, retrieval IDs, conversations, deletion and file delivery to a Django user or guest-session workspace. Guest identity stays with the session cookie and is not a cross-device account.

**What keeps it fast?** The embedding model is loaded once per process, cached model files and Chroma persist across restarts, uploads are deduplicated, background processing keeps the page interactive, relational chunk lookups are batched and Gemini receives a bounded context.

**What is left for production?** Broader OCR accuracy evaluation, durable background workers, stronger account/session lifecycle controls, deployment-specific security/rate/storage controls and larger retrieval-quality evaluation. Provider errors and quota limits remain external dependencies.
