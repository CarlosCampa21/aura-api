# app/domain/queries/schemas.py
from pydantic import BaseModel, EmailStr
from typing import Optional

class QueryCreate(BaseModel):
    usuario_correo: EmailStr
    pregunta: str
    respuesta: Optional[str] = None
    ts: Optional[str] = None  # ISO-8601 opcional

class QueryOut(BaseModel):
    usuario_correo: EmailStr
    pregunta: str
    respuesta: str
    ts: str
