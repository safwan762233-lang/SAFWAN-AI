import httpx
from .config import OLLAMA_BASE_URL, OLLAMA_MODEL, SYSTEM_PROMPT

class OllamaError(Exception):
    pass

async def list_models():
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
            return [m.get("name") for m in response.json().get("models", [])]
    except Exception as exc:
        raise OllamaError(f"Cannot reach Ollama at {OLLAMA_BASE_URL}: {exc}") from exc

async def chat(messages, model=None, business_context=None):
    payload = {
        "model": model or OLLAMA_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT + (
            "\n\nCURRENT BUSINESS DATA (authoritative snapshot; do not invent missing values):\n" + __import__("json").dumps(business_context, ensure_ascii=False)
            if business_context is not None else ""
        )}, *messages],
        "stream": False,
        "options": {"temperature": 0.35}
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=8)) as client:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"], data.get("model", payload["model"])
    except Exception as exc:
        raise OllamaError(f"AI request failed: {exc}") from exc
