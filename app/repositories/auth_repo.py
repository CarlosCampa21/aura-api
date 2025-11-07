"""Persistencia de autenticación y refresh tokens."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4
import hashlib
from bson import ObjectId
from datetime import datetime, timezone, timedelta

from app.infrastructure.db.mongo import get_db

USER_COLL = "user"
RT_COLL = "refresh_token"


def _dt(dt: datetime) -> datetime:
    # Asegura timezone-aware en UTC
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def find_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Busca usuario por email (email en minúsculas)."""
    return get_db()[USER_COLL].find_one({"email": email})


# Eliminado: búsqueda directa por google_id no se usa actualmente.


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Obtiene usuario por id (str)."""
    return get_db()[USER_COLL].find_one({"_id": ObjectId(user_id)})


def set_email_verified(user_id: str) -> None:
    """Marca email verificado y activa usuario."""
    get_db()[USER_COLL].update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"email_verified": True, "is_active": True, "updated_at": datetime.utcnow().isoformat()}},
    )


def set_email_verification_code(user_id: str, code_hash: str, expires_at: datetime) -> None:
    """Guarda hash de código OTP y expiración (aware UTC)."""
    get_db()[USER_COLL].update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "email_verify_code_hash": code_hash,
                "email_verify_code_expires_at": expires_at.astimezone(timezone.utc),
                "updated_at": datetime.utcnow().isoformat(),
            }
        },
    )


def clear_email_verification_code(user_id: str) -> None:
    """Elimina datos de verificación por código."""
    get_db()[USER_COLL].update_one(
        {"_id": ObjectId(user_id)},
        {"$unset": {"email_verify_code_hash": "", "email_verify_code_expires_at": ""}, "$set": {"updated_at": datetime.utcnow().isoformat()}},
    )


# Eliminado: actualización directa de password_hash no se usa actualmente.


def increment_token_version(user_id: str) -> None:
    """Incrementa token_version (invalidando access tokens previos)."""
    get_db()[USER_COLL].update_one(
        {"_id": ObjectId(user_id)}, {"$inc": {"token_version": 1}, "$set": {"updated_at": datetime.utcnow().isoformat()}}
    )


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token_doc(
    *,
    user_id: str,
    raw_token: str,
    family_id: Optional[str],
    rotation_parent_id: Optional[str],
    device_id: str,
    ip: str,
    user_agent: str,
    created_at: datetime,
    expires_at: datetime,
) -> Dict[str, Any]:
    """Construye documento listo para insertar en refresh_token (hash + metadatos)."""
    return {
        "user_id": ObjectId(user_id),
        "token_hash": _hash_refresh_token(raw_token),
        "family_id": family_id or str(uuid4()),
        "rotation_parent_id": ObjectId(rotation_parent_id) if rotation_parent_id else None,
        "device_id": device_id,
        "ip": ip,
        "user_agent": user_agent,
        "created_at": _dt(created_at),
        "expires_at": _dt(expires_at),
        "revoked_at": None,
        "revoked_reason": None,
    }


def insert_refresh_token(doc: Dict[str, Any]) -> str:
    """Inserta refresh_token y devuelve id (str)."""
    res = get_db()[RT_COLL].insert_one(doc)
    return str(res.inserted_id)


def get_refresh_token_by_hash(token_hash: str) -> Optional[Dict[str, Any]]:
    """Obtiene refresh_token por hash."""
    return get_db()[RT_COLL].find_one({"token_hash": token_hash})


def revoke_refresh_token(rt_id: str, reason: str) -> None:
    """Revoca un refresh_token por id con razón (marca revoked_at/Reason)."""
    get_db()[RT_COLL].update_one(
        {"_id": ObjectId(rt_id)},
        {"$set": {"revoked_at": _dt(datetime.utcnow()), "revoked_reason": reason}},
    )


def revoke_family(family_id: str, reason: str) -> None:
    """Revoca toda una familia de tokens (misma family_id)."""
    get_db()[RT_COLL].update_many(
        {"family_id": family_id, "revoked_at": None},
        {"$set": {"revoked_at": _dt(datetime.utcnow()), "revoked_reason": reason}},
    )


def get_child_refresh_token(parent_id: str) -> Optional[Dict[str, Any]]:
    """Obtiene el hijo directo de una rotación (si existe), más reciente.

    Útil para tolerar condiciones de carrera: si un refresh ya fue rotado,
    se puede continuar la rotación desde su hijo sin forzar logout.
    """
    return get_db()[RT_COLL].find_one(
        {"rotation_parent_id": ObjectId(parent_id)}, sort=[("created_at", -1)]
    )
