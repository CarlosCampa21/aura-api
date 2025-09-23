# app/infrastructure/ai/openai_client.py
from typing import Optional
from openai import OpenAI
from app.core.config import settings

_client: Optional[OpenAI] = None

def get_openai() -> Optional[OpenAI]:
    """
    Devuelve un cliente de OpenAI si hay API key en settings.
    Mantiene una instancia única en memoria.
    """
    global _client
    if _client is not None:
        return _client

    if not settings.openai_api_key:
        return None

    _client = OpenAI(api_key=settings.openai_api_key)
    return _client
