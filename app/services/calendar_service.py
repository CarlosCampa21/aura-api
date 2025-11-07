"""Servicio utilitario de calendario académico (asuetos).

Provee `is_holiday(date)` leyendo de una colección opcional `calendar_holiday`.
Si la colección no existe o no hay match exacto, retorna False sin fallar.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.infrastructure.db.mongo import get_db


def _date_key(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def is_holiday(d: datetime, campus: Optional[str] = None) -> bool:
    """Devuelve True si `d` aparece en `calendar_holiday.date`.

    Estructura sugerida del documento en `calendar_holiday`:
      { date: "YYYY-MM-DD", reason: str, campus: null|"La Paz"|... }
    """
    try:
        db = get_db()
        q = {"date": _date_key(d)}
        if campus:
            q["$or"] = [{"campus": campus}, {"campus": None}, {"campus": {"$exists": False}}]
        row = db["calendar_holiday"].find_one(q, {"_id": 1})
        return bool(row)
    except Exception:
        return False

