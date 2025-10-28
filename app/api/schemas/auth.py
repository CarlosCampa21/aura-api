"""
Esquemas Pydantic para operaciones de autenticación.

- Mantiene las validaciones y normalizaciones (p. ej. email en minúsculas).
- Modelos pensados para separar la capa API de la lógica de negocio.
"""

from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, field_validator, model_validator


class UserRegisterInput(BaseModel):
    """Datos mínimos para registrar un usuario.

    - `auth_provider` puede ser "local" o "google".
    - Si es "google" se requiere `google_id`.
    """

    email: EmailStr
    auth_provider: Literal["local", "google"]
    google_id: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: EmailStr) -> str:
        return str(v).lower()

    @model_validator(mode="after")
    def _check_google(self):
        if self.auth_provider == "google" and not self.google_id:
            raise ValueError("google_id requerido para auth_provider=google")
        return self


class RegisterPayload(BaseModel):
    """Payload de registro.

    - Para `local`: `password` es obligatorio.
    - Para `google`: `google_id` va dentro de `user`.
    """

    user: UserRegisterInput
    password: Optional[str] = None


class LoginLocalPayload(BaseModel):
    email: EmailStr
    password: str
    device_id: str


class LoginGooglePayload(BaseModel):
    email: EmailStr
    google_id: str
    device_id: str


class GoogleIdTokenPayload(BaseModel):
    id_token: str
    device_id: str


class SendVerificationPayload(BaseModel):
    email: Optional[EmailStr] = None
    verification_token: Optional[str] = None


class VerifyEmailCodePayload(BaseModel):
    verification_token: str
    code: str


class RefreshPayload(BaseModel):
    refresh_token: str
    device_id: str


class LogoutPayload(BaseModel):
    refresh_token: str


class ForceLogoutPayload(BaseModel):
    user_id: str


# === Response models ===

"""
