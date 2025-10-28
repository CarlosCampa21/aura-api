"""Endpoints de Aura (ask directo con orquestación mínima)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from app.services.ask_service import ask

router = APIRouter(prefix="/aura", tags=["Aura"])


class Ask(BaseModel):
    usuario_correo: EmailStr
    pregunta: str


@router.post("/ask", response_model=dict)
def aura_ask(payload: Ask):
    try:
        result = ask(str(payload.usuario_correo), payload.pregunta.strip())
        return {"message": "ok", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ask failed: {e}")
