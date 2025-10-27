"""
Dependencias y utilidades para validar access tokens y cargar usuario actual.
"""
from fastapi import Depends, HTTPException, Header
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from typing import Optional, Dict, Any

from app.services.token_service import verify_access_token
from app.repositories import auth_repository as repo


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Falta token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = verify_access_token(token)
    except Exception:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Token inválido")

    user_id = payload.get("sub")
    token_version = payload.get("token_version")
    if not user_id:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Token inválido")

    u = repo.get_user_by_id(user_id)
    if not u:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    if u.get("token_version", 0) != token_version:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Token expirado")
    if not u.get("is_active"):
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Usuario inactivo")
    if not u.get("email_verified"):
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Email no verificado")

    return u


def get_current_user_loose(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Igual que get_current_user pero sin exigir is_active ni email_verified.
    Útil para endpoints que deben funcionar para usuarios recién registrados
    (p. ej., chat) aunque aún no verifiquen el correo.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Falta token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = verify_access_token(token)
    except Exception:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Token inválido")

    user_id = payload.get("sub")
    token_version = payload.get("token_version")
    if not user_id:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Token inválido")

    u = repo.get_user_by_id(user_id)
    if not u:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    if u.get("token_version", 0) != token_version:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Token expirado")
    return u
