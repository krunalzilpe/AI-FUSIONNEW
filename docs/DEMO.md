# Folio walkthrough

1. Open a fresh workspace and ask a normal question without uploading a file.
2. Use **Understand a topic** for an explanation, or **Practice for exams** for a quiz. Give the student's class and subject; check the answer against their textbook.
3. Upload a short PDF with facts on known pages. Wait for processing, then select it and ask a factual question.
4. Click the answer's citation, compare the original passage, and open the PDF at that page.
5. Reopen the conversation to show that its source excerpts stay attached to the original answer.
6. Start a new conversation to chat without sources. Switch appearance and check the mobile layout.

The example in `assistant_app/test_fixtures.py` has a project budget of 750000 rupees on PDF page 2 and technical details on page 3. It is synthetic test data.

## Explain the project

- **Full stack:** Django views and services, SQLite records, vector retrieval, and a responsive browser interface.
- **Local inference:** an existing open-source Qwen instruction model runs through llama.cpp. Folio integrates the model; it does not claim to have trained a foundation model.
- **RAG:** document extraction, overlapping chunks, multilingual embeddings, scoped ChromaDB retrieval, and generation using the retrieved passages.
- **Citations:** original passages and physical PDF pages are saved with the answer. Citation-number checks validate references, but cannot prove every model claim.
- **Privacy:** each guest session has its own library and history. Files use an ownership-checked source endpoint.
- **Limits:** model answers can be wrong, long summaries sample excerpts, and live news is unavailable without a supplied article. The public quick-tunnel demo depends on the laptop staying online.
