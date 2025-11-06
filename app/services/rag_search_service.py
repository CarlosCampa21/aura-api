"""Búsqueda vectorial y redacción de respuesta "bonita" sin citar fuentes.

Mejora: enriquece los extractos con metadatos (título/tags) del documento para
dar más señal al LLM (ej., categoría "docentes", tag "dasc").
"""
from __future__ import annotations

from typing import List, Dict

from app.infrastructure.ai.embeddings import embed_texts
from app.repositories.library_chunk_repo import knn_search
from app.repositories.library_repo import get_document
from app.infrastructure.ai.openai_client import get_openai
from app.core.config import settings
from app.infrastructure.ai.ai_service import ask_llm


SYSTEM = (
    "Eres AURA. Responde en español, cordial y conciso (1–2 oraciones). "
    "No incluyas URLs ni referencias explícitas a 'fuentes'. "
    "Usa exclusivamente la evidencia provista (título, etiquetas, sección y extractos). "
    "Si la pregunta es de calendario/fechas y el contexto incluye 'Inicio de clases' o 'Inicio de labores', responde con la(s) fecha(s) correspondiente(s). "
    "Si preguntan 'inicio del semestre', interpreta como fecha de inicio de clases; si hay variantes (escolarizados / no escolarizados), acláralas brevemente. "
    "Si no hay evidencia suficiente, dilo con claridad."
)


def _build_context(snippets: List[str]) -> str:
    joined = "\n\n".join(snippets)
    return f"Extractos confiables (usa solo lo que veas):\n{joined}"


def answer_with_rag(question: str, k: int = 5) -> dict:
    """Realiza RAG: embedding de pregunta → knn → redacción sin fuentes."""
    vectors = embed_texts([question])
    qv = vectors[0] if vectors else []
    hits = knn_search(qv, k=max(k, 5))
    if not hits:
        # Sin contexto, usar LLM estándar para respuesta general
        text = ask_llm(question, "")
        return {"answer": text, "used_context": False}

    # Enriquecer con metadatos (título/tags) del documento
    # Permitir varios extractos por documento (máx 3) para evitar perder señales.
    MAX_SNIPPETS_PER_DOC = 3
    snippets: List[str] = []
    per_doc_count: Dict[str, int] = {}
    for h in hits:
        doc_id = str(h.get("doc_id"))
        if not doc_id:
            continue
        # Limita a N extractos por documento
        if per_doc_count.get(doc_id, 0) >= MAX_SNIPPETS_PER_DOC:
            continue
        meta_title = ""
        meta_tags: list[str] = []
        section = ""
        try:
            d = get_document(doc_id)
            if d:
                meta_title = str(d.get("title") or "")
                meta_tags = [str(t).lower() for t in (d.get("tags") or [])]
        except Exception:
            pass
        try:
            m = h.get("meta") or {}
            section = str(m.get("section") or "")
        except Exception:
            section = ""
        snippet_text = str(h.get("text") or "")
        # Arma línea con metadatos + extracto
        tag_str = ",".join(meta_tags) if meta_tags else ""
        prefix = f"titulo: {meta_title}"
        if tag_str:
            prefix += f" | etiquetas: {tag_str}"
        if section:
            prefix += f" | seccion: {section}"
        snippets.append(prefix + f"\nextracto: {snippet_text}")
        per_doc_count[doc_id] = per_doc_count.get(doc_id, 0) + 1
    ctx = _build_context(snippets)

    oa = get_openai()
    if oa:
        resp = oa.chat.completions.create(
            model=settings.openai_model_primary,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Contexto:\n{ctx}\n---\nPregunta: {question}"},
            ],
            temperature=0.2,
        )
        out = (resp.choices[0].message.content or "").strip()
        return {"answer": out or "Sin respuesta.", "used_context": True}

    # Fallback al pipeline genérico si no hay OpenAI
    text = ask_llm(question, ctx)
    return {"answer": text, "used_context": True}
