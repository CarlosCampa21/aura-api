# app/services/ask_service.py
from app.services.ai_service import ask_llm
from app.services.context_builder import build_academic_context
from app.services.schedule_service import try_answer_schedule
from app.services.tool_router import answer_with_tools

def ask(user_email: str, question: str) -> dict:
    """
    Construye contexto académico y pregunta al LLM, sin persistir en colecciones legacy.
    """
    # 1) Construye contexto breve
    ctx = build_academic_context(user_email)

    # 2) Si hay OpenAI, deja que el modelo decida tool/respuesta
    oa_answer = answer_with_tools(user_email, question, ctx)
    if oa_answer:
        return {
            "pregunta": question,
            "respuesta": oa_answer,
            "contexto_usado": True,
        }

    # 3) Fallback local: detector simple de horario
    tool_answer = try_answer_schedule(user_email, question)
    if tool_answer:
        return {
            "pregunta": question,
            "respuesta": tool_answer,
            "contexto_usado": True,
        }

    # 4) Último recurso: pipeline LLM clásico (OpenAI→Ollama)
    answer = ask_llm(question, ctx)
    return {
        "pregunta": question,
        "respuesta": answer,
        "contexto_usado": bool(ctx and ctx != "Sin datos académicos del alumno aún."),
    }
