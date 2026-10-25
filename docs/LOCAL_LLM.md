# Local model

Folio defaults to `LLM_PROVIDER=local`. Chat and document answers use a local llama.cpp server; no API key is sent and there is no automatic cloud fallback.

## Windows x64

```powershell
.\.venv\Scripts\python.exe scripts/setup_local_llm.py
.\.venv\Scripts\python.exe scripts/run_local.py
```

Setup downloads the Unsloth Q4_K_M quantization of Qwen3-4B-Instruct-2507 (about 2.5 GB) and the CPU build of llama.cpp into the ignored `.cache/local-llm/` directory. Both downloads are checked against SHA-256 digests. Keep these files: they are needed for offline inference. No system service or global model runtime is installed.

The launcher binds the model to `127.0.0.1:8081` and Folio to `127.0.0.1:8003`. It reuses a running server only if its model alias is `folio-local`. Ctrl+C stops processes owned by that launcher.

## Other operating systems

Install [llama.cpp](https://github.com/ggml-org/llama.cpp) for your OS and start a compatible server:

```sh
llama-server -hf unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M --alias folio-local --host 127.0.0.1 --port 8081 -c 8192 -np 1
python manage.py runserver 127.0.0.1:8003
```

## Configuration

| Variable | Default |
| --- | --- |
| LLM_PROVIDER | local |
| LOCAL_LLM_URL | http://127.0.0.1:8081 |
| LOCAL_LLM_MODEL | folio-local |
| LOCAL_LLM_TIMEOUT_SECONDS | 180 |
| LOCAL_LLM_MAX_TOKENS | 1024 |

Use an equivalent self-hosted chat-completions server by changing the URL/model. If the server is unreachable, Folio shows an error and retains retrieved passages instead of inventing a fallback answer. Local mode never uses an existing Gemini key.

Gemini is optional: set `LLM_PROVIDER=gemini`, configure `GEMINI_API_KEY` and an available `GEMINI_MODEL`, then restart. Provider failures and quota errors remain separate from insufficient document evidence.

Model source and license: [Qwen model card, Apache 2.0](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507). Runtime: [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases). This is integration of an existing model, not a claim that Folio trained its own LLM.
