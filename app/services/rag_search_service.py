"""Búsqueda vectorial y redacción de respuesta "bonita" sin citar fuentes.

Mejora: enriquece los extractos con metadatos (título/tags) del documento para
dar más señal al LLM (ej., categoría "docentes", tag "dasc").
"""
from __future__ import annotations

from typing import List, Optional
from datetime import datetime

from app.infrastructure.ai.embeddings import embed_texts
from app.repositories.library_chunk_repo import knn_search, list_texts_by_doc_id
from app.repositories.library_repo import get_document, search_documents
from app.infrastructure.ai.openai_client import get_openai
from app.core.config import settings
from app.infrastructure.ai.ai_service import ask_llm
from app.core.time import CODE_TO_SPANISH_DAY


SYSTEM_BASE = (
    "Eres AURA. Responde en español, con tono cercano y profesional. "
    "Redacta directo y natural, en 1–2 oraciones. "
    "Evita iniciar con 'Sí' o 'No' y evita muletillas. "
    "No incluyas URLs ni referencias a fuentes. "
    "Usa únicamente la evidencia provista (títulos, etiquetas y extractos). "
    "Si no hay evidencia suficiente, dilo de forma breve y clara."
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


def _polish_style(text: str) -> str:
    """Limpia muletillas comunes y asegura un cierre breve y natural.

    - Quita 'Sí,'/ 'Sí.' / 'No,' al inicio
    - Reduce a como máximo 2 oraciones
    - Normaliza espacios y asegura punto final
    """
    import re
    if not text:
        return text
    s = text.strip()
    s = re.sub(r"^\s*(s[ií])[\s,.:;-]+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*(no)[\s,.:;-]+", "", s, flags=re.IGNORECASE)
    # Mantén máximo 2 oraciones
    parts = re.split(r"(?<=[.!?])\s+", s)
    s = " ".join(parts[:2]).strip()
    # Normaliza espacios
    s = re.sub(r"\s+", " ", s)
    # Punto final si falta y no termina con signo
    if s and s[-1] not in ".!?":
        s += "."
    return s


def _normalize(s: str) -> str:
    import unicodedata, re
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def answer_with_rag(question: str, k: int = 5, *, entity_hint: Optional[str] = None) -> dict:
    """Realiza RAG: embedding de pregunta → knn → redacción sin fuentes."""
    normalized_q = _normalize_relative_dates(question)
    if entity_hint:
        normalized_q = f"{normalized_q} (persona_objetivo: {entity_hint})"
    vectors = embed_texts([normalized_q])
    qv = vectors[0] if vectors else []
    hits = knn_search(qv, k=max(k, 5))
    if not hits:
        # Sin contexto, usar LLM estándar para respuesta general
        text = ask_llm(question, "")
        return {"answer": text, "used_context": False}

    # Enriquecer con metadatos (título/tags) del documento
    snippets: List[str] = []
    enriched: List[dict] = []  # {doc_id, title, text}
    seen_docs: set[str] = set()
    target_norm = _normalize(entity_hint) if entity_hint else None
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
        # Si tenemos persona objetivo, intenta priorizar solo los extractos que la contengan
        if target_norm:
            body_norm = _normalize(meta_title + " " + snippet_text)
            if target_norm in body_norm:
                snippets.append(prefix + f"\nextracto: {snippet_text}")
                enriched.append({"doc_id": doc_id, "title": meta_title, "text": snippet_text})
        else:
            snippets.append(prefix + f"\nextracto: {snippet_text}")
            enriched.append({"doc_id": doc_id, "title": meta_title, "text": snippet_text})

    # Si filtramos por entidad y no quedó nada, usa los hits originales pero
    # deja claro al modelo que responda solo sobre la persona objetivo.
    if not snippets and hits:
        for h in hits[:k]:
            doc_id = str(h.get("doc_id"))
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
            tag_str = ",".join(meta_tags) if meta_tags else ""
            prefix = f"titulo: {meta_title}"
            if tag_str:
                prefix += f" | etiquetas: {tag_str}"
            snippets.append(prefix + f"\nextracto: {snippet_text}")
            enriched.append({"doc_id": doc_id, "title": meta_title, "text": snippet_text})

    # Intento directo de extraer email(s) de los extractos cuando hay persona objetivo
    import re as _re
    if entity_hint and enriched:
        email_re = _re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
        candidates: List[str] = []
        # 1) Correos encontrados en snippets ya filtrados
        for e in enriched:
            for m in email_re.findall(e.get("text") or ""):
                candidates.append(m)
        # 2) Si no hay, pero sabemos el doc, intenta leer más chunks del mismo doc
        if not candidates:
            # Busca un doc cuyo título contenga el nombre y lee sus chunks
            try:
                docs = search_documents(entity_hint, limit=3)
                for d in docs or []:
                    texts = list_texts_by_doc_id(d.get("id"))
                    for t in texts:
                        for m in email_re.findall(t or ""):
                            candidates.append(m)
                    if candidates:
                        break
            except Exception:
                pass
        # Si encontramos exactamente 1 correo, respondemos directo
        uniq = []
        seen = set()
        for c in candidates:
            if c not in seen:
                uniq.append(c)
                seen.add(c)
        if len(uniq) == 1:
            return {"answer": _polish_style(f"El correo de {entity_hint} es {uniq[0]}."), "used_context": True}
    ctx = _build_context(snippets)

    oa = get_openai()
    system = SYSTEM_BASE + f" Fecha actual: {_today_spanish()}."
    if entity_hint:
        system += (
            f" Persona objetivo: '{entity_hint}'. Responde exclusivamente sobre esa persona. "
            "Si un extracto contiene varias personas, elige solo la información de la persona objetivo; "
            "si no aparece, indica brevemente que no está disponible."
        )
    if oa:
        resp = oa.chat.completions.create(
            model=settings.openai_model_primary,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Contexto:\n{ctx}\n---\nPregunta: {normalized_q}"},
            ],
            temperature=0.4,
        )
        out = (resp.choices[0].message.content or "").strip()
        return {"answer": _polish_style(out) or "Sin respuesta.", "used_context": True}

    # Fallback al pipeline genérico si no hay OpenAI
    text = ask_llm(question, ctx)
    return {"answer": _polish_style(text), "used_context": True}
