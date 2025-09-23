# app/domain/notes/schemas.py
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional

class NoteCreate(BaseModel):
    usuario_correo: EmailStr
    titulo: str
    contenido: str
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None  # ISO-8601 opcional

class NoteOut(BaseModel):
    usuario_correo: EmailStr
    titulo: str
    contenido: str
    tags: List[str]
    created_at: str
