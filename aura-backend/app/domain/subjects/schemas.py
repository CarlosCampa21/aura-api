# app/domain/subjects/schemas.py
from pydantic import BaseModel, Field
from typing import List

class SubjectCreate(BaseModel):
    codigo: str
    nombre: str
    profesor: str
    salon: str
    dias: List[str] = Field(default_factory=list)   # ej. ["Lun","Mie"]
    hora_inicio: str                                # "08:00"
    hora_fin: str                                   # "09:30"

class SubjectOut(BaseModel):
    codigo: str
    nombre: str
    profesor: str
    salon: str
    dias: List[str]
    hora_inicio: str
    hora_fin: str
