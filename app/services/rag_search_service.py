"""Búsqueda vectorial y redacción de respuesta "bonita" sin citar fuentes.

Mejora: enriquece los extractos con metadatos (título/tags) del documento para
dar más señal al LLM (ej., categoría "docentes", tag "dasc").
"""
from __future__ import annotations

from typing import List
from datetime import datetime

from app.infrastructure.ai.embeddings import embed_texts
from app.repositories.library_chunk_repo import knn_search
from app.repositories.library_repo import get_document
from app.infrastructure.ai.openai_client import get_openai
from app.core.config import settings
from app.infrastructure.ai.ai_service import ask_llm
from app.core.time import CODE_TO_SPANISH_DAY


SYSTEM_BASE = (
    "Eres AURA. Responde en español, cordial y conciso, en una o dos oraciones. "
    "No incluyas URLs, ni citas, ni referencias a fuentes. "
    "Usa exclusivamente la evidencia provista (títulos, etiquetas y extractos). "
    "Si el nombre de una persona aparece en el título o el extracto, responde en afirmativo con 'Sí' y resume su rol/áreas. "
    "Solo menciona 'DASC' si aparece explícito en el texto o en las etiquetas. "
    "Si no hay evidencia sobre la persona preguntada, indica que no tienes datos suficientes."
)


def _build_context(snippets: List[str]) -> str:
    joined = "\n\n".join(snippets)
    return f"Extractos confiables (usa solo lo que veas):\n{joined}"


def _today_spanish() -> str:
    now = datetime.now()
    day_name = CODE_TO_SPANISH_DAY[["mon","tue","wed","thu","fri","sat","sun"][now.weekday()]].capitalize()
    months = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
    return f"{day_name} {now.day} de {months[now.month-1]} de {now.year}"


def _normalize_relative_dates(question: str) -> str:
    """Convierte expresiones como 'este 17 de noviembre' a '17 de noviembre de YYYY'."""
    import re
    q = question or ""
    year = datetime.now().year
    # solo cuando aparece 'este'/'próximo' para no forzar otras frases
    pattern = re.compile(r"\b(este|pr[oó]ximo)\s+(\d{1,2})\s+de\s+([a-záéíóú]+)\b", re.IGNORECASE)
    def repl(m):
        return f"{m.group(2)} de {m.group(3)} de {year}"
    q2 = pattern.sub(repl, q)
    return q2


def answer_with_rag(question: str, k: int = 5) -> dict:
    """Realiza RAG: embedding de pregunta → knn → redacción sin fuentes."""
    normalized_q = _normalize_relative_dates(question)
    vectors = embed_texts([normalized_q])
    qv = vectors[0] if vectors else []
    hits = knn_search(qv, k=max(k, 5))
    if not hits:
        # Sin contexto, usar LLM estándar para respuesta general
        text = ask_llm(question, "")
        return {"answer": text, "used_context": False}

    # Enriquecer con metadatos (título/tags) del documento
    snippets: List[str] = []
    seen_docs: set[str] = set()
    for h in hits:
        doc_id = str(h.get("doc_id"))
        if not doc_id:
            continue
        # Limita a un extracto por documento para diversidad
        if doc_id in seen_docs:
            continue
        seen_docs.add(doc_id)
        meta_title = ""
        meta_tags: list[str] = []
        try:
            d = get_document(doc_id)
            if d:
                meta_title = str(d.get("title") or "")
                meta_tags = [str(t).lower() for t in (d.get("tags") or [])]
        except Exception:
            pass
        snippet_text = str(h.get("text") or "")
        # Arma línea con metadatos + extracto
        tag_str = ",".join(meta_tags) if meta_tags else ""
        prefix = f"titulo: {meta_title}"
        if tag_str:
            prefix += f" | etiquetas: {tag_str}"
        snippets.append(prefix + f"\nextracto: {snippet_text}")
    ctx = _build_context(snippets)

    oa = get_openai()
    system = SYSTEM_BASE + f" Fecha actual: {_today_spanish()}."
    if oa:
        resp = oa.chat.completions.create(
            model=settings.openai_model_primary,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Contexto:\n{ctx}\n---\nPregunta: {normalized_q}"},
            ],
            temperature=0.2,
        )
        out = (resp.choices[0].message.content or "").strip()
        return {"answer": out or "Sin respuesta.", "used_context": True}

    # Fallback al pipeline genérico si no hay OpenAI
    text = ask_llm(question, ctx)
    return {"answer": text, "used_context": True}
