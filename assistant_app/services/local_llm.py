"""Talk to a locally hosted llama.cpp model; no API credentials are used."""
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


class LocalModelError(Exception):
    pass


def generate(prompt):
    payload = {
        "model": settings.LOCAL_LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.1,
        "max_tokens": settings.LOCAL_LLM_MAX_TOKENS,
        "stream": False,
    }
    key = settings.LOCAL_LLM_API_KEY
    key_file = Path(settings.BASE_DIR) / ".cache" / "local-llm" / "api-key"
    if not key and key_file.exists():
        key = key_file.read_text(encoding="utf8").strip()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    request = Request(
        settings.LOCAL_LLM_URL.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.LOCAL_LLM_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read(2 * 1024 * 1024))
        choice = result["choices"][0]
        answer = choice["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Empty local response")
        if choice.get("finish_reason") == "length":
            answer += "\n\n(Response length limit reached. Ask me to continue.)"
        return answer.strip()
    except HTTPError as exc:
        if exc.code == 503:
            raise LocalModelError("Folio is getting ready or handling another question. Please retry shortly.") from exc
        raise LocalModelError("Folio could not complete this request. Try a shorter question or fewer documents.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise LocalModelError("Folio is unavailable right now. Please try again in a moment.") from exc
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LocalModelError("Folio could not prepare an answer. Please try again.") from exc
