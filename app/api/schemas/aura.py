"""Schemas para endpoints de Aura (ask directo)."""
from pydantic import BaseModel, EmailStr


class Ask(BaseModel):
    usuario_correo: EmailStr
    pregunta: str


class AuraAskOut(BaseModel):
    message: str
    pregunta: str
    respuesta: str
    contexto_usado: bool

