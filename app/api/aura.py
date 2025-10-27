# app/api/aura.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from app.services.ask_service import ask

router = APIRouter(prefix="/aura", tags=["Aura"])

class Ask(BaseModel):
    usuario_correo: EmailStr
    pregunta: str

@router.post("/ask")
def aura_ask(payload: Ask):
    """
    Orquesta el caso de uso:
      - Construye contexto
      - Pregunta al LLM (OpenAI→fallback→Ollama)
      - No persiste en colecciones legacy; la persistencia ocurre vía /chat/messages
    """
    try:
        result = ask(str(payload.usuario_correo), payload.pregunta.strip())
        return {"message": "ok", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ask failed: {e}")
