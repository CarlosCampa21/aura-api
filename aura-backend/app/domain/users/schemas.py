# app/domain/users/schemas.py
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    nombre: str
    correo: EmailStr
    carrera: str
    semestre: int = Field(ge=1, description="Semestre >= 1")

class UserOut(BaseModel):
    nombre: str
    correo: EmailStr
    carrera: str
    semestre: int
