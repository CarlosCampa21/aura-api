"""Repo de la colección"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.infrastructure.db.mongo import get_db

COLLECTION = "note"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_note(doc: Dict[str, Any]) -> str:
    """Inserta nota con defaults y devuelve id (str)."""
    db = get_db()
    data = dict(doc)
    now = _now_iso()
    data.setdefault("status", "active")
    data.setdefault("source", "manual")
    data.setdefault("tags", [])
    data.setdefault("created_at", now)
    data["updated_at"] = now
    res = db[COLLECTION].insert_one(data)
    return str(res.inserted_id)


def list_notes(user_id: Optional[str] = None, status: Optional[str] = None, tag: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista notas por filtros básicos (ordenadas por updated_at desc)."""
    db = get_db()
    filtro: Dict[str, Any] = {}
    if user_id:
        filtro["user_id"] = str(user_id)
    if status:
        filtro["status"] = status
    if tag:
        filtro["tags"] = str(tag).lower()
    projection = {"_id": 0}
    return list(db[COLLECTION].find(filtro, projection).sort("updated_at", -1))
