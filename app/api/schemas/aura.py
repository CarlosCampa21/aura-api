"""Esquemas para endpoints de Aura (ask directo)."""
from pydantic import BaseModel, EmailStr


class Ask(BaseModel):
    usuario_correo: EmailStr
    pregunta: str

