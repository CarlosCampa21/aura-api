"""Orquestación de preguntas del usuario hacia el asistente (IA + tools)."""
from app.infrastructure.ai.ai_service import ask_llm
from app.services.context_service import build_academic_context
from app.services.schedule_service import try_answer_schedule
from app.infrastructure.ai.tools.router import answer_with_tools
import re
from app.services.rag_search_service import answer_with_rag
from app.core.time import now_text, now_time_text, now_date_text
from typing import Optional, List, Dict, Any


_NAME_RE = re.compile(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})\b")


def _extract_person_hint(prev_text: Optional[str]) -> Optional[str]:
    """Extrae un posible nombre propio (2–4 palabras capitalizadas) del texto previo."""
    if not prev_text:
        return None
    m = None
    for m in _NAME_RE.finditer(prev_text):
        pass
    if m:
        return m.group(1)
    return None


def _extract_person_from_history(history: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Busca el último nombre propio en los últimos turnos de la conversación.

    Revisa hasta ~6 mensajes previos (usuario y asistente) para detectar un
    nombre de 2–4 palabras capitalizadas y lo usa como foco.
    """
    if not history:
        return None
    tail = list(history)[-6:]
    for msg in reversed(tail):
        txt = str(msg.get("content") or "")
        hint = _extract_person_hint(txt)
        if hint:
            return hint
    return None


def ask(user_email: str, question: str, *, prev_text: Optional[str] = None, prev_messages: Optional[List[Dict[str, Any]]] = None, entity_focus: Optional[str] = None) -> dict:
    """Construye contexto y responde usando tool‑calling u LLM.

    Flujo:
    1) Construye contexto académico breve
    2) Intenta tool‑calling (get_schedule/get_now)
    3) Fallback local de horario
    4) Fallback LLM (OpenAI→Ollama)
    """
    # 1) Construye contexto breve
    ctx = build_academic_context(user_email)

    # 2) Short-circuit: preguntas directas de fecha/hora
    qlow = (question or "").lower().strip()
    # Solo hora
    if re.search(r"\b(qu[eé]\s*hora\s*es|hora\s*actual)\b", qlow):
        text_now = now_time_text(user_email)
        return {
            "pregunta": question,
            "respuesta": text_now,
            "contexto_usado": True,
            "attachments": _extract_urls(text_now),
        }

    # Solo fecha/día
    if re.search(r"\b(que\s*d[ií]a\s*es\s*hoy|qu[eé]\s*fecha\s*es)\b", qlow):
        text_now = now_date_text(user_email)
        return {
            "pregunta": question,
            "respuesta": text_now,
            "contexto_usado": True,
            "attachments": _extract_urls(text_now),
        }

    # Resolución ligera de referencia: si el usuario usa "su" o pronombres,
    # aprovecha el último nombre detectado en el turno previo.
    name_hint = None
    if re.search(r"\b(su\s+(correo|email|nombre)|y\s+cu[aá]l\s+es\s+su)\b", qlow):
        name_hint = entity_focus or _extract_person_hint(prev_text) or _extract_person_from_history(prev_messages)
    else:
        # Si la pregunta es muy corta y no menciona sujeto, intenta tomar foco del historial
        if len(qlow.split()) <= 4 and not _extract_person_hint(question):
            name_hint = entity_focus or _extract_person_from_history(prev_messages)
        # Heurística: si menciona 'correo' o 'contacto' y no da nombre, hereda foco
        if ("correo" in qlow or "contact" in qlow) and not name_hint:
            name_hint = entity_focus or _extract_person_from_history(prev_messages)

    # 2) RAG primero: si hay evidencia útil, nos quedamos con esa respuesta
    try:
        q_eff = question
        if name_hint:
            q_eff = f"{question} (Se refiere a: {name_hint})"
        rag = answer_with_rag(q_eff, k=5, entity_hint=name_hint)
        if rag and rag.get("used_context") and rag.get("answer"):
            ans = str(rag.get("answer") or "")
            return {
                "pregunta": question,
                "respuesta": ans,
                "contexto_usado": True,
                "attachments": _extract_urls(ans),
            }
    except Exception:
        pass

    # 2b) Si no hubo contexto del RAG, dejamos que el modelo decida tool/respuesta
    oa_answer = answer_with_tools(user_email, question, ctx)
    if oa_answer:
        return {
            "pregunta": question,
            "respuesta": oa_answer,
            "contexto_usado": True,
            "attachments": _extract_urls(oa_answer),
        }

    # 3) Fallback local: detector simple de horario
    tool_answer = try_answer_schedule(user_email, question)
    if tool_answer:
        return {
            "pregunta": question,
            "respuesta": tool_answer,
            "contexto_usado": True,
            "attachments": _extract_urls(tool_answer),
        }

    # 4) Último recurso: pipeline LLM clásico (OpenAI→Ollama)
    answer = ask_llm(question, ctx)
    return {
        "pregunta": question,
        "respuesta": answer,
        "contexto_usado": bool(ctx and ctx != "Sin datos académicos del alumno aún."),
        "attachments": _extract_urls(answer),
    }


_URL_RE = re.compile(r"https?://[^\s>]+", re.IGNORECASE)


def _extract_urls(text: str) -> list[str]:
    """Extrae URLs del texto para adjuntarlas en el mensaje.

    Filtra si hay una base pública de R2 configurada; en caso contrario, devuelve todas las URLs detectadas.
    """
    if not text:
        return []
    urls = _URL_RE.findall(text)
    try:
        from app.infrastructure.storage.r2 import public_base_url

        base = public_base_url() or ""
        if base:
            urls = [u for u in urls if u.startswith(base)]
    except Exception:
        pass
    # Dedup conservando orden
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out
