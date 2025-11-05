"""Helpers para generar embeddings con OpenAI.

Usa el cliente singleton definido en `openai_client`. Lanza errores claros
si no hay configuración de OpenAI.
"""
from __future__ import annotations

from typing import List
from app.infrastructure.ai.openai_client import get_openai
from app.core.config import settings


def embed_texts(texts: List[str]) -> List[list[float]]:
    """Genera embeddings para una lista de textos.

    Devuelve una lista paralela de vectores (list[float]).
    """
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI no configurado para embeddings")
    if not texts:
        return []
    client = get_openai()
    if client is None:
        raise RuntimeError("OpenAI client no disponible")

    # OpenAI acepta lote de strings directamente
    resp = client.embeddings.create(
        model=settings.openai_embeddings_model,
        input=texts,
    )
    # Asegura orden
    vectors: List[list[float]] = [list(d.embedding) for d in resp.data]
    return vectors

