"""Endpoints de Aura (ask directo con orquestación mínima)."""
from fastapi import APIRouter, HTTPException
from app.services.ask_service import ask
from app.api.schemas.aura import Ask

router = APIRouter(prefix="/aura", tags=["Aura"])


@router.post(
    "/ask",
    response_model=dict,
    summary="Pregunta rápida a Aura",
    description="Construye contexto, pregunta al LLM y devuelve respuesta (sin persistencia).",
)
def aura_ask(payload: Ask):
    try:
        result = ask(str(payload.usuario_correo), payload.pregunta.strip())
        return {"message": "ok", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo procesar la pregunta: {e}")
