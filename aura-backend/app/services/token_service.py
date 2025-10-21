"""
Creación y verificación de JWTs para acceso y flujos de verificación.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import uuid4

# Asegura que usamos PyJWT (no el paquete "jwt" incorrecto)
try:
    import jwt as pyjwt  # PyJWT expone jwt.encode/jwt.decode
    if not hasattr(pyjwt, "encode"):
        raise ImportError("Paquete 'jwt' incorrecto en el entorno")
except Exception as e:
    raise RuntimeError(
        "Conflicto de librerías JWT: instala PyJWT>=2 y desinstala el paquete 'jwt'. "
        "Ejecuta: pip uninstall jwt && pip install PyJWT==2.9.0"
    ) from e

from app.core.config import settings


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(*, user: Dict[str, Any]) -> str:
    """
    Genera un JWT con HS256 válido por ACCESS_TOKEN_EXPIRE_MINUTES.
    Claims: sub(user_id), email, token_version, iat, exp, jti.
    """
    now = _now_utc()
    exp = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user["_id"]),
        "email": user.get("email"),
        "token_version": user.get("token_version", 0),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid4()),
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token


def verify_access_token(token: str) -> Dict[str, Any]:
    """
    Decodifica y valida firma/expiración. Devuelve payload.
    """
    return pyjwt.decode(token, key=settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def create_email_code_token(*, user_id: str, expires_in_minutes: int | None = None) -> str:
    """
    Token corto (no de acceso) para el flujo de verificación por código.
    Claims: sub(user_id), purpose=email_code, iat, exp, jti.
    """
    now = _now_utc()
    mins = expires_in_minutes if expires_in_minutes is not None else settings.email_code_expire_minutes
    exp = now + timedelta(minutes=mins)
    payload = {
        "sub": user_id,
        "purpose": "email_code",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid4()),
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_email_code_token(token: str) -> Dict[str, Any]:
    payload = pyjwt.decode(token, key=settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose") != "email_code":
        raise ValueError("Token de verificación inválido")
    return payload
