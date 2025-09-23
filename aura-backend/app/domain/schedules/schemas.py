# app/domain/schedules/schemas.py
from pydantic import BaseModel, EmailStr
from typing import Optional

class ScheduleCreate(BaseModel):
    usuario_correo: EmailStr
    materia_codigo: str
    dia: str                 # "Lun", "Mar", etc.
    hora_inicio: str         # "08:00"
    hora_fin: str            # "09:30"

class ScheduleFilter(BaseModel):
    usuario_correo: Optional[EmailStr] = None
