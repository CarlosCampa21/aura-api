"""
Repositorio para la colección `user`.
"""
from typing import List, Dict, Any
from datetime import datetime, timezone
from app.infrastructure.db.mongo import get_db

COLLECTION = "user"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_user(doc: Dict[str, Any]) -> str:
    """
    Inserta un usuario en la colección `user` y retorna el string del inserted_id.
    - Normaliza `email` a minúsculas.
    - Define valores por defecto (is_active, email_verified, token_version).
    - Sella `created_at` y `updated_at` en ISO-8601 UTC.
    """
    db = get_db()
    data = dict(doc)  # copia defensiva

    # Normaliza email
    if "email" in data and data["email"]:
        data["email"] = str(data["email"]).lower()

    # Defaults de flags
    data.setdefault("email_verified", False)
    data.setdefault("token_version", 0)

    # is_active: false hasta verificar correo; con Google puede activarse al login.
    # Al crear por esta ruta lo dejamos coherente con la regla.
    if data.get("auth_provider") == "google":
        data.setdefault("is_active", True)  # activo tras login con Google
    else:
        data.setdefault("is_active", False)

    # Timestamps
    now = _now_iso()
    data.setdefault("created_at", now)
    data["updated_at"] = now

    # Preferences por defecto si falta
    profile = data.get("profile")
    if isinstance(profile, dict):
        prefs = profile.get("preferences")
        if not isinstance(prefs, dict):
            profile["preferences"] = {"language": "es"}
        data["profile"] = profile

    res = db[COLLECTION].insert_one(data)
    return str(res.inserted_id)


def list_users() -> List[Dict[str, Any]]:
    """
    Lista user excluyendo campos sensibles y `_id`.
    """
    db = get_db()
    projection = {
        "_id": 0,
        "password_hash": 0,  # no exponer
        # `google_id` puede considerarse sensible; omitir por defecto
        "google_id": 0,
    }
    return list(db[COLLECTION].find({}, projection))
