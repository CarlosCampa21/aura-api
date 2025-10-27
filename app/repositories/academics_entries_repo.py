"""
Repositorio para `timetable_entry` y lógica de inferencia de turno.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.infrastructure.db.mongo import get_db
from bson import ObjectId
from .academics_timetables_repo import set_shift_if_missing

COLL = "timetable_entry"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_minutes(hhmm: str) -> int:
    try:
        h = int(hhmm[:2]); m = int(hhmm[3:])
        return h * 60 + m
    except Exception:
        return 0


def insert_entries_bulk(timetable_id: str, entries: List[Dict[str, Any]]) -> int:
    db = get_db()
    now = _now_iso()
    data: List[Dict[str, Any]] = []
    for e in entries:
        item = dict(e)
        item.setdefault("modality", "class")
        item.setdefault("module", None)
        item.setdefault("notes", None)
        item["timetable_id"] = str(timetable_id)
        item.setdefault("created_at", now)
        item["updated_at"] = now
        data.append(item)
    if not data:
        return 0
    db[COLL].insert_many(data)

    # Inferencia de turno (TM/TV) si falta en timetable: promedio de horas de inicio
    try:
        mins = [_to_minutes(x.get("start_time", "00:00")) for x in data]
        avg = sum(mins) / max(len(mins), 1)
        inferred = "TV" if avg >= 16 * 60 else "TM"
        set_shift_if_missing(timetable_id, inferred)
    except Exception:
        pass
    return len(data)


def list_entries(timetable_id: str) -> List[Dict[str, Any]]:
    db = get_db()
    docs = list(db[COLL].find({"timetable_id": str(timetable_id)}).sort([("day", 1), ("start_time", 1)]))
    out: List[Dict[str, Any]] = []
    for d in docs:
        d = dict(d)
        d.pop("_id", None)
        out.append(d)
    return out

