"""
Servicio de hora/fecha actual en la zona horaria del usuario.
Pensado para ser invocado como tool por el modelo (get_now).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app.infrastructure.db.mongo import get_db


CODE_TO_SPANISH_DAY = {
    "mon": "Lunes",
    "tue": "Martes",
    "wed": "Miércoles",
    "thu": "Jueves",
    "fri": "Viernes",
    "sat": "Sábado",
    "sun": "Domingo",
}


def _weekday_code(d: datetime) -> str:
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][d.weekday()]


def now_text(email: Optional[str] = None, tz_override: Optional[str] = None) -> str:
    """
    Devuelve una frase corta con la fecha/hora actuales en la TZ del usuario
    (o en `tz_override` si se especifica).
    """
    tz = tz_override
    if not tz and email:
        try:
            u = get_db()["user"].find_one({"email": email}, {"profile": 1}) or {}
            tz = ((u.get("profile") or {}).get("tz")) or None
        except Exception:
            tz = None

    try:
        now = datetime.now(ZoneInfo(tz)) if tz else datetime.now()
    except Exception:
        now = datetime.now()
        tz = None

    code = _weekday_code(now)
    day_es = CODE_TO_SPANISH_DAY.get(code, code).capitalize()
    date_s = now.strftime("%Y-%m-%d")
    time_s = now.strftime("%H:%M")
    iso_s = now.isoformat()
    tz_s = tz or "(hora del servidor)"
    return f"Ahora es {day_es} {date_s} {time_s} en {tz_s} (ISO {iso_s})."

