"""
Repositorio para la colección `conversations`.

- Guarda `user_id` como string (ObjectId serializado) para consistencia con otras refs.
- Sella timestamps en ISO-8601 UTC (Z) y mantiene `last_message_at`.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.infrastructure.db.mongo import get_db
from bson import ObjectId

COLLECTION = "conversations"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_conversation(doc: Dict[str, Any]) -> str:
    db = get_db()
    data = dict(doc)
    now = _now_iso()
    # Defaults
    data.setdefault("status", "active")
    data.setdefault("model", "gpt-4o-mini")
    data.setdefault("title", "")
    data.setdefault("settings", None)
    data.setdefault("metadata", None)
    data.setdefault("last_message_at", now)
    data.setdefault("created_at", now)
    data["updated_at"] = now

    res = db[COLLECTION].insert_one(data)
    return str(res.inserted_id)


def list_conversations(user_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    db = get_db()
    filtro: Dict[str, Any] = {}
    if user_id:
        filtro["user_id"] = str(user_id)
    if status:
        filtro["status"] = status
    projection = {"_id": 0}
    return list(db[COLLECTION].find(filtro, projection).sort("updated_at", -1))


def update_conversation_meta(conversation_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Actualiza campos de metadatos (title, status, settings, metadata)."""
    db = get_db()
    set_ops: Dict[str, Any] = {"updated_at": _now_iso()}
    for k in ["title", "status", "settings", "metadata", "last_message_at"]:
        if k in updates:
            set_ops[k] = updates[k]
    db[COLLECTION].update_one({"_id": ObjectId(conversation_id)}, {"$set": set_ops})
    # No devolvemos el doc para evitar 2 lecturas; los callers pueden listar
    return set_ops
