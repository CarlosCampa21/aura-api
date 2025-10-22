# app/services/ask_service.py
from app.services.ai_service import ask_llm
from app.services.context_builder import build_academic_context

def ask(user_email: str, question: str) -> dict:
    """
    Construye contexto académico y pregunta al LLM, sin persistir en colecciones legacy.
    """
    ctx = build_academic_context(user_email)
    answer = ask_llm(question, ctx)
    return {
        "pregunta": question,
        "respuesta": answer,
        "contexto_usado": bool(ctx and ctx != "Sin datos académicos del alumno aún."),
    }
