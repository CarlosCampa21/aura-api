"""Orquestación de preguntas del usuario hacia el asistente (IA + tools)."""
from app.infrastructure.ai.ai_service import ask_llm
from app.services.context_service import build_academic_context
from app.services.schedule_service import try_answer_schedule
from app.infrastructure.ai.tools.router import answer_with_tools
import re
from app.services.rag_search_service import answer_with_rag


def ask(user_email: str, question: str, history: list[dict] | None = None) -> dict:
    """Construye contexto y responde usando tool‑calling u LLM.

    Flujo:
    1) Construye contexto académico breve
    2) Intenta tool‑calling (get_schedule/get_now)
    3) Fallback local de horario
    4) Fallback LLM (OpenAI→Ollama)
    """
    # 1) Construye contexto breve
    ctx = build_academic_context(user_email)

    # 2) RAG primero: si hay evidencia útil, nos quedamos con esa respuesta
    try:
        rag = answer_with_rag(question, k=5)
        if rag and rag.get("used_context") and rag.get("answer"):
            ans = str(rag.get("answer") or "")
            return {
                "pregunta": question,
                "respuesta": ans,
                "contexto_usado": True,
                "came_from": rag.get("came_from") or "rag",
                "citation": rag.get("citation") or "",
                "source_chunks": rag.get("source_chunks") or [],
                "followup": rag.get("followup") or "",
                "attachments": _extract_urls(ans),
            }
    except Exception:
        pass

    # 2b) Si no hubo contexto del RAG, dejamos que el modelo decida tool/respuesta
    oa_answer = answer_with_tools(user_email, question, ctx, history=history)
    if oa_answer and isinstance(oa_answer, dict) and (oa_answer.get("answer") or "").strip():
        return {
            "pregunta": question,
            "respuesta": oa_answer.get("answer") or "",
            "contexto_usado": True,
            "came_from": oa_answer.get("origin") or "tool",
            "citation": "",
            "source_chunks": [],
            "followup": _suggest_followup_tool(question, oa_answer.get("origin")),
            "attachments": _extract_urls(str(oa_answer.get("answer") or "")),
        }

    # 3) Fallback local: detector simple de horario
    tool_answer = try_answer_schedule(user_email, question)
    if tool_answer:
        return {
            "pregunta": question,
            "respuesta": tool_answer,
            "contexto_usado": True,
            "came_from": "schedule",
            "citation": "",
            "source_chunks": [],
            "followup": "¿Quieres que te comparta también tus clases de mañana?",
            "attachments": _extract_urls(tool_answer),
        }

    # 4) Último recurso: pipeline LLM clásico (OpenAI→Ollama)
    answer = ask_llm(question, ctx, history=history)
    return {
        "pregunta": question,
        "respuesta": answer,
        "contexto_usado": bool(ctx and ctx != "Sin datos académicos del alumno aún."),
        "came_from": "llm",
        "citation": "",
        "source_chunks": [],
        "followup": "¿Deseas que busque un documento oficial relacionado?",
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


def _suggest_followup_tool(question: str, origin: str | None) -> str:
    if origin and origin.startswith("tool:get_schedule"):
        return "¿Quieres que te recuerde tus próximas clases?"
    if origin and origin.startswith("tool:get_document"):
        return "¿Deseas que te comparta el enlace al documento en PDF?"
    return "¿Deseas que amplíe con información relacionada?"
