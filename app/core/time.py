"""
Servicio de hora/fecha actual en la zona horaria del usuario.

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


def get_user_tz(email: Optional[str]) -> Optional[str]:
    """Obtiene la zona horaria del perfil del usuario (o None si no existe)."""
    if not email:
        return None
    try:
        u = get_db()["user"].find_one({"email": email}, {"profile": 1}) or {}
        return ((u.get("profile") or {}).get("tz")) or None
    except Exception:
        return None


def now_text(email: Optional[str] = None, tz_override: Optional[str] = None) -> str:
    """
    Devuelve una frase amigable con la fecha y hora actuales.

    - Prefiere la zona horaria del usuario (perfil) o `tz_override` si se pasa.
    - Formato en español, sin detalles técnicos (sin ISO ni "hora del servidor").
    """
    tz = tz_override or get_user_tz(email)

    try:
        now = datetime.now(ZoneInfo(tz)) if tz else datetime.now()
    except Exception:
        now = datetime.now()
        tz = None

    code = _weekday_code(now)
    day_es = CODE_TO_SPANISH_DAY.get(code, code).capitalize()
    months = [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]
    date_human = f"{day_es} {now.day} de {months[now.month - 1]} de {now.year}"
    time_human = now.strftime("%H:%M")

    return f"Hoy es {date_human} y son las {time_human}."


def now_time_text(email: Optional[str] = None, tz_override: Optional[str] = None) -> str:
    """Devuelve solo la hora local en formato amigable."""
    tz = tz_override or get_user_tz(email)
    try:
        now = datetime.now(ZoneInfo(tz)) if tz else datetime.now()
    except Exception:
        now = datetime.now()
    return now.strftime("Son las %H:%M.")


def now_date_text(email: Optional[str] = None, tz_override: Optional[str] = None) -> str:
    """Devuelve solo la fecha local en formato amigable."""
    tz = tz_override or get_user_tz(email)
    try:
        now = datetime.now(ZoneInfo(tz)) if tz else datetime.now()
    except Exception:
        now = datetime.now()
    day_es = CODE_TO_SPANISH_DAY[["mon","tue","wed","thu","fri","sat","sun"][now.weekday()]].capitalize()
    months = [
        "enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre",
    ]
    return f"Hoy es {day_es} {now.day} de {months[now.month-1]} de {now.year}."
