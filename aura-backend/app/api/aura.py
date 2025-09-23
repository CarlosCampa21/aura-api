# app/api/aura.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from app.services.ask_service import ask_and_store

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
      - Guarda en Mongo 'consultas'
    """
    try:
        result = ask_and_store(str(payload.usuario_correo), payload.pregunta.strip())
        return {"message": "Consulta registrada", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ask failed: {e}")
