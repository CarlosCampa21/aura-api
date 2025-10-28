"""
Esquemas Pydantic para la colección `user`.

Reglas clave:
- Campos en snake_case.
- `email` se guarda siempre en minúsculas.
- Autenticación: `auth_provider` en {"local", "google"}.
  - Si `local` -> requiere `password_hash`.
  - Si `google` -> requiere `google_id`.
- Timestamps en ISO-8601 UTC.
"""

from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class Preferences(BaseModel):
    language: str = Field(default="es")


class UserProfile(BaseModel):
    full_name: Optional[str] = None
    student_id: Optional[str] = None
    major: Optional[str] = None  # e.g., IDS, ITC, IC, LATI, LITI
    semester: Optional[int] = Field(default=None, ge=1)
    shift: Optional[str] = None  # TM, TV
    group: Optional[str] = None  # e.g., A, B
    tz: Optional[str] = None  # America/Mazatlan
    phone: Optional[str] = None
    birthday: Optional[str] = None  # ISO date (YYYY-MM-DD)
    preferences: Optional[Preferences] = Field(default_factory=Preferences)

class UserProfileUpdate(BaseModel):
    """
    Esquema para actualización parcial del perfil.
    Nota: no aplicamos default a preferences para no sobreescribir accidentalmente.
    """
    full_name: Optional[str] = None
    student_id: Optional[str] = None
    major: Optional[str] = None
    semester: Optional[int] = Field(default=None, ge=1)
    shift: Optional[str] = None
    group: Optional[str] = None
    tz: Optional[str] = None
    phone: Optional[str] = None
    birthday: Optional[str] = None
    preferences: Optional[Preferences] = None


class UserBase(BaseModel):
    email: EmailStr
    auth_provider: Literal["local", "google"]
    password_hash: Optional[str] = None  # solo si auth_provider = 'local'
    google_id: Optional[str] = None      # solo si auth_provider = 'google'

    is_active: bool = False
    email_verified: bool = False
    token_version: int = 0

    profile: Optional[UserProfile] = None

    created_at: Optional[str] = None  # ISO-8601 UTC
    updated_at: Optional[str] = None  # ISO-8601 UTC

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: EmailStr) -> str:
        return str(v).lower()

    @model_validator(mode="after")
    def _validate_auth_fields(self):
        if self.auth_provider == "local" and not self.password_hash:
            raise ValueError("password_hash es requerido cuando auth_provider='local'")
        if self.auth_provider == "google" and not self.google_id:
            raise ValueError("google_id es requerido cuando auth_provider='google'")
        return self


# Nota: La creación de usuarios se realiza vía `/auth/register`.
# Si en el futuro se expone un endpoint administrativo para creación directa,
# se puede reintroducir un esquema específico (p. ej., `AdminUserCreate`).


class UserOut(BaseModel):
    """Respuesta pública de usuario (sin secretos)."""
    email: EmailStr
    auth_provider: Literal["local", "google"]
    is_active: bool
    email_verified: bool
    token_version: int
    profile: Optional[UserProfile] = None
    created_at: str
    updated_at: str

