# app/services/ask_service.py
from datetime import datetime
from app.services.ai_service import ask_llm
from app.services.context_builder import build_academic_context
from app.infrastructure.db.mongo import get_db

def ask_and_store(user_email: str, question: str) -> dict:
    """
    Construye contexto académico, pregunta al LLM y guarda la consulta en Mongo.
    Retorna payload listo para responder al cliente.
    """
    ctx = build_academic_context(user_email)
    answer = ask_llm(question, ctx)

    db = get_db()
    ins = db["consultas"].insert_one({
        "usuario_correo": user_email,
        "pregunta": question,
        "respuesta": answer,
        "ts": datetime.utcnow().isoformat(),
    })

    return {
        "id": str(ins.inserted_id),
        "pregunta": question,
        "respuesta": answer,
        "contexto_usado": bool(ctx and ctx != "Sin datos académicos del alumno aún."),
    }
