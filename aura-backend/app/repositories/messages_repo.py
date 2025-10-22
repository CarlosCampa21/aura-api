"""
Repositorio para la colección `messages`.

- Inserta mensajes y actualiza `last_message_at`/`updated_at` en la conversación.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.infrastructure.db.mongo import get_db
from bson import ObjectId

COLLECTION = "messages"
CONV_COLLECTION = "conversations"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_message(doc: Dict[str, Any]) -> str:
    db = get_db()
    data = dict(doc)
    now = _now_iso()
    # Defaults opcionales
    data.setdefault("attachments", [])
    data.setdefault("citations", [])
    data.setdefault("model_snapshot", None)
    data.setdefault("tokens_input", None)
    data.setdefault("tokens_output", None)
    data.setdefault("error", None)
    data.setdefault("created_at", now)

    res = db[COLLECTION].insert_one(data)

    # Actualiza conversación: last_message_at y updated_at
    try:
        db[CONV_COLLECTION].update_one(
            {"_id": ObjectId(str(data.get("conversation_id")))},
            {"$set": {"last_message_at": now, "updated_at": now}},
        )
    except Exception:
        # No romper la inserción si falla la actualización cruzada
        pass

    return str(res.inserted_id)


def list_messages(conversation_id: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    db = get_db()
    filtro: Dict[str, Any] = {}
    if conversation_id:
        filtro["conversation_id"] = str(conversation_id)
    if user_id:
        filtro["user_id"] = str(user_id)
    projection = {"_id": 0}
    return list(db[COLLECTION].find(filtro, projection).sort("created_at", 1))

