"""Búsqueda vectorial y redacción de respuesta "bonita" sin citar fuentes.

Mejora: enriquece los extractos con metadatos (título/tags) del documento para
dar más señal al LLM (ej., categoría "docentes", tag "dasc").
"""
from __future__ import annotations

from typing import List, Dict
from datetime import datetime
import re

from app.infrastructure.ai.embeddings import embed_texts
from app.repositories.library_chunk_repo import knn_search
from app.repositories.library_repo import get_document
from app.infrastructure.ai.openai_client import get_openai
from app.core.config import settings
from app.infrastructure.ai.ai_service import ask_llm


SYSTEM = (
    "Usa únicamente la información del contexto para responder. "
    "Responde con un tono cordial e institucional. "
    "Da una respuesta clara y concisa con la información encontrada. "
    "No inventes información fuera del contexto disponible. "
    "No incluyas citas, referencias ni el nombre del documento fuente. "
    "Si no aparece la respuesta en el contexto, dilo con claridad y ofrece ayuda para buscarla. "
    "No sugieras consultar sitios web externos; pide un dato mínimo para continuar o indica que seguirás buscando. "
    "No hagas suposiciones ni inventes datos."
)



def _build_context(snippets: List[str]) -> str:
    joined = "\n\n".join(snippets)
    return f"Extractos confiables (usa solo lo que veas):\n{joined}"


def _strip_markdown_styles(text: str) -> str:
    """Elimina marcadores Markdown básicos para respuestas planas."""
    if not text:
        return text
    out = text
    out = re.sub(r"\*\*([^\*\n]+)\*\*", r"\1", out)
    out = re.sub(r"__([^_\n]+)__", r"\1", out)
    out = re.sub(r"\*([^\*\n]+)\*", r"\1", out)
    out = re.sub(r"_([^_\n]+)_", r"\1", out)
    out = re.sub(r"`([^`]+)`", r"\1", out)
    return out


def answer_with_rag(question: str, k: int = 5, *, return_sources: bool = False, continuation_person: str | None = None) -> dict:
    """Realiza RAG: embedding de pregunta → knn → redacción sin fuentes."""
    q_for_embed = _rewrite_query_people(question)
    vectors = embed_texts([q_for_embed])
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
    # Para salida enriquecida (deshabilitado para UI: no citamos fuentes)
    source_chunks: List[Dict[str, str]] = []
    per_doc_count: Dict[str, int] = {}
    # Prefetch títulos para un reordenamiento ligero por nombre
    title_cache: Dict[str, str] = {}
    q_low = (question or "").lower()
    name_tokens = [t for t in re.findall(r"[a-záéíóúñ]{3,}", q_low) if t not in {"quien", "quién", "que", "qué", "hace", "correo", "email", "de", "la", "el"}]
    # Obtén títulos y calcula pequeño boost por coincidencia en título
    def _boost(h: dict) -> int:
        did = str(h.get("doc_id") or "")
        if not did:
            return 0
        if did not in title_cache:
            try:
                d = get_document(did)
                title_cache[did] = (d.get("title") if d else "") or ""
            except Exception:
                title_cache[did] = ""
        title = title_cache.get(did, "").lower()
        return sum(1 for t in name_tokens if t and t in title)

    wants_email = any(w in q_low for w in ("correo", "email", "e-mail", "mail"))
    is_dept_head_query = ("jefe" in q_low and "depart" in q_low)

    def _token_score(h: dict) -> int:
        txt = (h.get("text") or "").lower()
        score = 0
        if wants_email and "@" in txt:
            score += 2
        if is_dept_head_query and ("jefe" in txt and "depart" in txt):
            score += 2
        if "dasc" in q_low and ("dasc" in txt or "sistemas computacionales" in txt):
            score += 1
        return score

    if name_tokens or wants_email or is_dept_head_query:
        hits.sort(key=lambda h: (_boost(h), _token_score(h), float(h.get("score", 0.0))), reverse=True)

    # Si buscamos correo/jefatura y aún no hay candidatos con tokens relevantes, amplía k y reintenta ordenar
    if (wants_email or is_dept_head_query) and not any(_token_score(h) > 0 for h in hits):
        extra = knn_search(qv, k=max(eff_k, 100))
        if extra:
            hits = extra
            # recalcular caches
            title_cache = {}
            def _boost2(h: dict) -> int:
                did = str(h.get("doc_id") or "")
                if not did:
                    return 0
                if did not in title_cache:
                    try:
                        d = get_document(did)
                        title_cache[did] = (d.get("title") if d else "") or ""
                    except Exception:
                        title_cache[did] = ""
                title = title_cache.get(did, "").lower()
                return sum(1 for t in name_tokens if t and t in title)
            hits.sort(key=lambda h: (_boost2(h), _token_score(h), float(h.get("score", 0.0))), reverse=True)

    for h in hits:
        doc_id = str(h.get("doc_id"))
        if not doc_id:
            continue
        # Limita a N extractos por documento
        if per_doc_count.get(doc_id, 0) >= MAX_SNIPPETS_PER_DOC:
            continue
        meta_title = title_cache.get(doc_id, "") if title_cache else ""
        meta_tags: list[str] = []
        section = ""
        if not meta_title:
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
    # Instrucción dinámica de ‘hoy’ para preferir fechas futuras
    months = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
        7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
    }
    now = datetime.now()
    today_es = f"{now.day} de {months.get(now.month, now.month)} de {now.year}"
    system_dyn = (
        SYSTEM
        + " Hoy es "
        + today_es
        + ". Si el contexto muestra varias fechas, elige la más próxima posterior a hoy."
        + " Si todas las fechas de una sección ya pasaron, indícalo brevemente y menciona la siguiente programada si existe."
    )

    # Modo de respuesta breve para consultas sobre docentes/perfiles
    if any(w in q_low for w in ("profe", "profesor", "profesora", "docente")):
        system_dyn += (
            " Para preguntas sobre docentes, responde en 1–2 oraciones máximas: "
            "nombre (si aplica), rol y áreas de especialidad. "
            "Si hay un correo institucional (dominio 'uabcs.mx'), compártelo al final. "
            "Evita copiar párrafos largos del contexto y no incluyas notas de fuente."
        )
    if any(w in q_low for w in ("quien es", "quién es", "que hace", "qué hace")):
        system_dyn += (
            " Responde con un perfil breve: cargo actual (si aparece), departamento o unidad, y 2–4 áreas clave. "
            "Mantén la salida en una o dos frases claras."
        )
    # Si la conversación ya identificó a la persona, evita repetir el nombre completo
    if continuation_person:
        system_dyn += (
            f" En esta conversación ya hablamos de '{continuation_person}'. "
            "Evita repetir su nombre completo en cada respuesta; usa pronombres (él/ella) o 'el profesor/la profesora' si queda claro."
        )
    # Si piden correos explícitamente, regresa solo el correo (o 'No encontrado')
    if any(w in q_low for w in ("correo", "email", "e-mail")):
        system_dyn += (
            " Si la pregunta pide un correo, responde únicamente el correo institucional "
            "tal como aparezca en el contexto (por ejemplo, usuario@uabcs.mx). "
            "Si hay varios en el contexto, entrega solo el que corresponda al docente referido en la pregunta. "
            "Si no es posible determinarlo, indica brevemente que necesitas el nombre completo."
        )
    if oa:
        resp = oa.chat.completions.create(
            model=settings.openai_model_primary,
            messages=[
                {"role": "system", "content": system_dyn},
                {"role": "user", "content": f"Contexto:\n{ctx}\n---\nPregunta: {question}"},
            ],
            temperature=getattr(settings, "rag_temperature", settings.chat_temperature),
            top_p=settings.chat_top_p,
            presence_penalty=settings.chat_presence_penalty,
            frequency_penalty=settings.chat_frequency_penalty,
        )
        out = (resp.choices[0].message.content or "").strip()
        out = _strip_markdown_styles(out)
        followup = "¿Puedo ayudarte con otra cosa?" if settings.chat_followups_enabled else ""
        # Nota: no devolvemos citas ni chunks para evitar paréntesis en UI
        return {"answer": out or "Sin respuesta.", "used_context": True, "came_from": "rag", "citation": "", "source_chunks": (source_chunks if return_sources else []), "followup": followup}

    # Fallback al pipeline genérico si no hay OpenAI
    text = ask_llm(question, ctx, system=system_dyn)
    text = _strip_markdown_styles(text)
    followup = "¿Puedo ayudarte con otra cosa?" if settings.chat_followups_enabled else ""
    return {"answer": text, "used_context": True, "came_from": "rag", "citation": "", "source_chunks": (source_chunks if return_sources else []), "followup": followup}


def _suggest_followup(question: str) -> str:
    q = (question or "").lower()
    if "semestre" in q or "inicio" in q:
        return "¿Quieres que te muestre el PDF oficial del calendario?"
    if "semana santa" in q:
        return "¿Quieres ver el calendario completo?"
    if "septiembre" in q or "asueto" in q or "clases" in q:
        return "¿Deseas que también te comparta las fechas de exámenes ordinarios?"
    return "¿Quieres que te comparta el documento oficial relacionado?"


def _rewrite_query_people(q: str) -> str:
    s = q or ""
    low = s.lower()
    parts = [s]
    # Si la consulta parece nombre de persona, añade rol académico para sesgar recuperación
    name_like = len(re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", s)) >= 2
    if name_like and not any(w in low for w in ("profesor", "profesora", "profe", "maestro", "jefe", "doctor", "docente")):
        parts.append("perfil académico UABCS, profesor, docente, jefe de departamento, doctor")
    # Rol: jefe de departamento → añade sinónimos comunes
    if ("jefe" in low and "depart" in low):
        parts.append("jefe de departamento, jefatura, director de departamento, titular del departamento, responsable del departamento, Departamento Académico")
    # Departamento DASC → añade nombre largo y sin siglas
    if "dasc" in low:
        parts.append("Departamento Académico de Sistemas Computacionales, DASC, Sistemas Computacionales")
    if any(w in low for w in ("correo", "email", "e-mail", "mail")):
        parts.append("correo institucional @uabcs.mx")
    return "; ".join(parts)
