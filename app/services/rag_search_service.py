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
    "Usa únicamente la información del contexto para responder. "
    "Responde con un tono cordial e institucional. "
    "Da una respuesta clara y completa con la información encontrada. "
    "Al final incluye entre paréntesis una cita breve indicando el origen del dato "
    "(ejemplo: Calendario Escolar UABCS 2025 — Actividades 2025-II). "
    "No inventes información fuera del contexto disponible. "
    "Si no aparece la respuesta en el contexto, dilo con claridad y ofrece ayuda para buscarla."
)



def _build_context(snippets: List[str]) -> str:
    joined = "\n\n".join(snippets)
    return f"Extractos confiables (usa solo lo que veas):\n{joined}"


def answer_with_rag(question: str, k: int = 5) -> dict:
    """Realiza RAG: embedding de pregunta → knn → redacción sin fuentes."""
    vectors = embed_texts([question])
    qv = vectors[0] if vectors else []
    # Usa k por parámetro o default desde settings
    eff_k = int(k or 0) or settings.rag_k_default
    hits = knn_search(qv, k=max(eff_k, 5))
    if not hits:
        # Sin contexto, usar LLM estándar para respuesta general
        text = ask_llm(question, "")
        return {"answer": text, "used_context": False}

    # Enriquecer con metadatos (título/tags) del documento
    # Permitir varios extractos por documento (configurable) para no perder señales.
    MAX_SNIPPETS_PER_DOC = max(1, int(getattr(settings, "rag_snippets_per_doc", 3)))
    snippets: List[str] = []
    # Para salida enriquecida
    source_chunks: List[Dict[str, str]] = []
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
        # Guardar fuente enriquecida para UI (recorta extracto)
        source_chunks.append({
            "doc_id": doc_id,
            "title": meta_title,
            "section": section,
            "chunk_index": str(h.get("chunk_index", 0)),
            "score": f"{float(h.get('score', 0.0)):.4f}",
            "text": (snippet_text[:280] + "…") if len(snippet_text) > 280 else snippet_text,
        })
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
            temperature=settings.chat_temperature,
            top_p=settings.chat_top_p,
            presence_penalty=settings.chat_presence_penalty,
            frequency_penalty=settings.chat_frequency_penalty,
        )
        out = (resp.choices[0].message.content or "").strip()
        # Citation: usa el primer chunk como referencia
        citation = ""
        if source_chunks:
            t = source_chunks[0].get("title") or ""
            s = source_chunks[0].get("section") or ""
            citation = f"{t} — {s}".strip(" —")
        followup = _suggest_followup(question)
        return {"answer": out or "Sin respuesta.", "used_context": True, "came_from": "rag", "citation": citation, "source_chunks": source_chunks[:3], "followup": followup}

    # Fallback al pipeline genérico si no hay OpenAI
    text = ask_llm(question, ctx)
    citation = ""
    if source_chunks:
        t = source_chunks[0].get("title") or ""
        s = source_chunks[0].get("section") or ""
        citation = f"{t} — {s}".strip(" —")
    followup = _suggest_followup(question)
    return {"answer": text, "used_context": True, "came_from": "rag", "citation": citation, "source_chunks": source_chunks[:3], "followup": followup}


def _suggest_followup(question: str) -> str:
    q = (question or "").lower()
    if "semestre" in q or "inicio" in q:
        return "¿Quieres que te muestre el PDF oficial del calendario?"
    if "semana santa" in q:
        return "¿Quieres ver el calendario completo?"
    if "septiembre" in q or "asueto" in q or "clases" in q:
        return "¿Deseas que también te comparta las fechas de exámenes ordinarios?"
    return "¿Quieres que te comparta el documento oficial relacionado?"
