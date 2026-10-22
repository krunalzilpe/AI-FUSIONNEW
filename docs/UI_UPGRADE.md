# Light theme and answer audio — 22 October 2026

Implemented in the existing Django/Bootstrap/vanilla JavaScript interface. No backend, RAG, schema, API credentials or application dependencies changed.

## Changed files

- `templates/assistant_app/dashboard.html`: prepaint light default, visible sidebar appearance selector, labeled upload/question controls and toolbar SVG icons.
- `static/assistant_app/style.css`: light/dark color tokens, blue/lavender/teal accents, readable answer/source cards, larger controls, focus states and responsive refinements. Reduced-motion support retained.
- `static/assistant_app/workspace.js`: synchronized persisted theme selectors; per-answer Listen/Stop, Copy, View/Hide Sources and Regenerate; playback cleanup on navigation. Regenerate adds a new answer using the original document IDs, preserves prior answers and disables itself when an original document is unavailable.
- `static/assistant_app/speech.js`: browser speech controller, Markdown/citation cleanup, language/voice selection, bounded utterances, cancellation, stale-event protection and actionable error/fallback messages.
- `scripts/test_speech.cjs`, `scripts/test_workspace_ui.cjs`: audio controller and simulated DOM regression tests.

## Executed verification

| Status | Result |
| --- | --- |
| PASS | Django system check; no pending model changes from `makemigrations --check --dry-run`. |
| PASS | 46 Django regression tests. |
| PASS | 7 real local RAG integration tests; 2 live-Gemini tests explicitly skipped. English, Hinglish, Hindi and Marathi sample questions retrieved the correct PDF page. |
| PASS | 18 JavaScript tests: audio start/stop/switch/finish/errors, asynchronous voice loading, local-only policy, language fallback, light default, saved dark theme, copy success/denial, message-specific sources, regeneration scope/duplicate prevention and unavailable document/API error states. |
| PASS | JavaScript syntax checks. |
| PASS | Actual HTTP PDF/TXT upload, asynchronous extraction/embedding/indexing, duplicate detection, retrieval-only chat, physical page-2 citation, history restoration, source access isolation and synthetic test-data cleanup. |
| NOT TESTED | Visual desktop/mobile layout, actual device audio/pronunciation and native PDF navigation: connected browser inventory was empty. DOM tests simulate behavior and do not render a browser. |
| NOT TESTED | Live Gemini generation and deployment for this upgrade. Earlier provider availability/quota failures recorded in `VERIFICATION.md` are not resolved by a UI change. |

## Audio behavior and privacy

Only voices with `localService === true` are eligible. This property distinguishes local from remote synthesis services ([MDN documentation](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/localService)). No Gemini, cloud TTS, microphone or other network request is triggered by Listen. With no local voice, Listen is disabled and an explanation is visible; the interface responds to delayed `voiceschanged` events.

Hindi/Marathi voices are selected when installed. Roman Hinglish prefers Indian English, with an explicit pronunciation limitation. If the language is unavailable, another local voice is used with a notice. Availability and pronunciation depend on the browser and OS; no universal language support is claimed.

## Repeating tests

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py test assistant_app.tests assistant_app.tests_features
.venv\Scripts\python.exe -X utf8 test_rag_pipeline.py
node --test scripts/test_speech.cjs
# Optional DOM test tooling, isolated from application dependencies:
npm.cmd install --prefix .local-backup/ui-test-tools --no-save --package-lock=false --ignore-scripts jsdom@27.0.1
node --test scripts/test_workspace_ui.cjs
```

Before presenting, refresh the app, inspect both themes at desktop and phone widths, and exercise Listen/Stop on two answers. Check installed Hindi/Marathi voices if those languages are part of the demo. Restore Gemini availability and rerun the live suite (`test_rag_pipeline.py --gemini`) before claiming the generation demo is ready.
