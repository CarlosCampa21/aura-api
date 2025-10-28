"""Cliente HTTP mínimo para Ollama (chat y helper ask)."""
import requests
from app.core.config import settings

def ollama_chat(messages: list[dict], temperature: float = 0.2, timeout: int | None = None) -> str:
    """
    Llama al endpoint /api/chat de Ollama.
    messages: [{"role":"system","content":"..."}, {"role":"user","content":"..."}]
    Retorna el texto de la respuesta (string limpio).
    """
    r = requests.post(
        f"{settings.ollama_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=timeout or settings.ollama_timeout_seconds,
    )
    r.raise_for_status()
    data = r.json()
    return ((data.get("message") or {}).get("content") or "").strip()


def ollama_ask(system: str, user: str, temperature: float = 0.2, timeout: int | None = None) -> str:
    """
    Atajo: arma los mensajes system+user y llama a ollama_chat.
    """
    return ollama_chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        timeout=timeout or settings.ollama_timeout_seconds,
    )
