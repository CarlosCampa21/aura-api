"""Repo para `timetable` (cabecera de horario) y utilidades relacionadas."""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from app.infrastructure.db.mongo import get_db
from bson import ObjectId

COLL = "timetable"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _key(doc: Dict[str, Any]) -> Tuple[str, str, int, str, str]:
    return (
        str(doc.get("department_code")),
        str(doc.get("program_code")),
        int(doc.get("semester")),
        str(doc.get("group")),
        str(doc.get("period_code")),
    )


def insert_timetable(doc: Dict[str, Any]) -> str:
    """Inserta un timetable (status draft por defecto) y devuelve su id (str)."""
    db = get_db()
    data = dict(doc)
    now = _now_iso()
    data.setdefault("status", "draft")
    data.setdefault("version", 1)
    data.setdefault("is_current", False)
    # title por defecto
    if not data.get("title"):
        data["title"] = f"{data.get('program_code', '').upper()} {data.get('semester')} {data.get('shift') or ''} Grupo {data.get('group', '').upper()} {data.get('period_code')}".strip()
    data.setdefault("created_at", now)
    data["updated_at"] = now
    res = db[COLL].insert_one(data)
    return str(res.inserted_id)


def publish_timetable(timetable_id: str) -> None:
    """Publica un timetable y marca `is_current=True` desmarcando otros de la misma combinación."""
    db = get_db()
    now = _now_iso()
    # Encuentra doc para saber combinación
    cur = db[COLL].find_one({"_id": ObjectId(timetable_id)})
    if not cur:
        return
    # Desmarca otros como current en misma combinación
    db[COLL].update_many(
        {
            "_id": {"$ne": ObjectId(timetable_id)},
            "department_code": cur.get("department_code"),
            "program_code": cur.get("program_code"),
            "semester": cur.get("semester"),
            "group": cur.get("group"),
            "period_code": cur.get("period_code"),
        },
        {"$set": {"is_current": False}},
    )
    # Marca published
    db[COLL].update_one(
        {"_id": ObjectId(timetable_id)},
        {"$set": {"status": "published", "is_current": True, "published_at": now, "updated_at": now}},
    )


def list_timetables(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Lista timetables filtrando por combinación; expone `id` como str y ordena por current/updated_at."""
    db = get_db()
    q: Dict[str, Any] = {}
    for k in ["department_code", "program_code", "semester", "group", "period_code", "status", "is_current", "shift"]:
        if k in filters and filters[k] is not None:
            q[k] = filters[k]
    docs = list(db[COLL].find(q).sort([("is_current", -1), ("updated_at", -1)]))
    out: List[Dict[str, Any]] = []
    for d in docs:
        d = dict(d)
        d["id"] = str(d.pop("_id"))
        out.append(d)
    return out


def set_shift_if_missing(timetable_id: str, inferred: Optional[str]) -> None:
    """Establece `shift` solo si no existe aún (helper usado por entries)."""
    if not inferred:
        return
    db = get_db()
    db[COLL].update_one(
        {"_id": ObjectId(timetable_id), "$or": [{"shift": None}, {"shift": {"$exists": False}}]},
        {"$set": {"shift": inferred, "updated_at": _now_iso()}},
    )
