"""
Lógica de autenticación: registro, login, refresh, logout, force-logout.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4
import secrets
import hashlib
from bson import ObjectId

from argon2 import PasswordHasher
from argon2.low_level import Type

from app.core.config import settings
from app.repositories import auth_repository as repo
from app.services.token_service import create_access_token


ph = PasswordHasher(time_cost=2, memory_cost=51200, parallelism=2, hash_len=32, salt_len=16, type=Type.ID)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _refresh_token_exp() -> datetime:
    return _now_utc() + timedelta(days=settings.refresh_token_expire_days)


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except Exception:
        return False


def generate_refresh_token() -> str:
    # 256-bit random token in hex
    return secrets.token_hex(32)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_for_user(
    *, user_id: str, device_id: str, ip: str, user_agent: str, family_id: Optional[str] = None, rotation_parent_id: Optional[str] = None
) -> Tuple[str, str]:
    """
    Crea un refresh token (raw) y guarda su hash. Devuelve (raw_token, refresh_id).
    """
    raw = generate_refresh_token()
    doc = repo.create_refresh_token_doc(
        user_id=user_id,
        raw_token=raw,
        family_id=family_id,
        rotation_parent_id=rotation_parent_id,
        device_id=device_id,
        ip=ip,
        user_agent=user_agent,
        created_at=_now_utc(),
        expires_at=_refresh_token_exp(),
    )
    refresh_id = repo.insert_refresh_token(doc)
    return raw, refresh_id


def rotate_refresh_token(*, current_raw: str, device_id: str, ip: str, user_agent: str) -> Tuple[str, str]:
    """
    Valida el refresh actual (hash), lo revoca y crea uno nuevo de la misma familia.
    Devuelve (new_raw, new_refresh_id).
    """
    current = repo.get_refresh_token_by_hash(_hash(current_raw))
    if not current:
        raise ValueError("Refresh token desconocido")
    if current.get("revoked_at") is not None:
        raise ValueError("Refresh token revocado")
    if current.get("expires_at") <= _now_utc():
        raise ValueError("Refresh token expirado")

    repo.revoke_refresh_token(str(current["_id"]), reason="rotated")

    new_raw, new_id = create_refresh_for_user(
        user_id=str(current["user_id"]),
        device_id=device_id,
        ip=ip,
        user_agent=user_agent,
        family_id=current["family_id"],
        rotation_parent_id=str(current["_id"]),
    )
    return new_raw, new_id


def logout_refresh_token(*, current_raw: str) -> None:
    current = repo.get_refresh_token_by_hash(_hash(current_raw))
    if current:
        repo.revoke_refresh_token(str(current["_id"]), reason="logout")


def login_local(*, email: str, password: str, device_id: str, ip: str, user_agent: str) -> Dict[str, Any]:
    u = repo.find_user_by_email(email.lower())
    if not u or u.get("auth_provider") != "local":
        raise ValueError("Credenciales inválidas")
    if not u.get("password_hash") or not verify_password(password, u.get("password_hash")):
        raise ValueError("Credenciales inválidas")

    access = create_access_token(user=u)
    refresh_raw, _ = create_refresh_for_user(
        user_id=str(u["_id"]), device_id=device_id, ip=ip, user_agent=user_agent
    )
    return {"access_token": access, "refresh_token": refresh_raw}


def login_google(*, google_id: str, email: str, device_id: str, ip: str, user_agent: str) -> Dict[str, Any]:
    u = repo.find_user_by_email(email.lower())
    if not u or u.get("auth_provider") != "google" or u.get("google_id") != google_id:
        raise ValueError("Credenciales inválidas")
    access = create_access_token(user=u)
    refresh_raw, _ = create_refresh_for_user(
        user_id=str(u["_id"]), device_id=device_id, ip=ip, user_agent=user_agent
    )
    return {"access_token": access, "refresh_token": refresh_raw}


def force_logout_all(*, user_id: str) -> None:
    repo.increment_token_version(user_id)
    # Opcional: revocar familia(s) activas del usuario

