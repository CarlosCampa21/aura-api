"""Herramientas de consulta de horario (timetable) para preguntas del alumno.

Expone funciones puras para:
- Detectar intención de consulta de horario en español.
- Resolver "qué clase me toca ahora/hoy/mañana/lunes..." con datos en Mongo.

No requiere al LLM: responde de forma determinista si hay datos suficientes.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

from app.infrastructure.db.mongo import get_db
from app.services.calendar_service import is_holiday
import unicodedata
import re


SPANISH_DAY_TO_CODE = {
    # lower -> Day (domain uses mon..sat)
    "lunes": "mon",
    "martes": "tue",
    "miercoles": "wed",
    "miércoles": "wed",
    "jueves": "thu",
    "viernes": "fri",
    "sabado": "sat",
    "sábado": "sat",
}

CODE_TO_SPANISH_DAY = {
    "mon": "Lunes",
    "tue": "Martes",
    "wed": "Miércoles",
    "thu": "Jueves",
    "fri": "Viernes",
    "sat": "Sábado",
}


def _now_in_tz(tz: str | None) -> datetime:
    try:
        if tz:
            return datetime.now(ZoneInfo(tz))
    except Exception:
        pass
    # Fallback: hora local del sistema
    return datetime.now()


def _weekday_code(d: datetime) -> str:
    # Python: Monday=0
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][d.weekday()]


def _time_to_minutes(hhmm: str) -> int:
    try:
        return int(hhmm[:2]) * 60 + int(hhmm[3:])
    except Exception:
        return 0


def _fmt_entry(e: Dict[str, Any]) -> str:
    room = f" {e.get('room_code')}" if e.get("room_code") else ""
    teacher = f" — {e.get('instructor')}" if e.get("instructor") else ""
    return f"{e['start_time']}-{e['end_time']} {e['course_name']}{room}{teacher}"


def _norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _get_user_profile(email: str) -> Dict[str, Any]:
    db = get_db()
    u = db["user"].find_one({"email": email}, {"_id": 0, "profile": 1}) or {}
    return u.get("profile") or {}


def _get_current_timetable(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    db = get_db()
    q: Dict[str, Any] = {
        "department_code": "DASC",
        "program_code": str(profile.get("major") or "").upper() or None,
        "semester": profile.get("semester"),
        "is_current": True,
    }
    if profile.get("shift"):
        q["shift"] = profile.get("shift")
    if profile.get("group"):
        q["group"] = profile.get("group")
    # limpia None
    q = {k: v for k, v in q.items() if v is not None}
    if not q.get("program_code") or not q.get("semester"):
        return None
    doc = db["timetable"].find_one(q)
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc


def _list_entries(timetable_id: str) -> List[Dict[str, Any]]:
    db = get_db()
    items = list(
        db["timetable_entry"].find({"timetable_id": str(timetable_id)}).sort([("day", 1), ("start_time", 1)])
    )
    for x in items:
        x.pop("_id", None)
    return items


def classes_for_day(email: str, d: datetime) -> Tuple[str, List[Dict[str, Any]]]:
    profile = _get_user_profile(email)
    tt = _get_current_timetable(profile)
    if not tt:
        return ("", [])
    entries = _list_entries(tt["id"]) 
    day_code = _weekday_code(d)
    day_entries = [e for e in entries if e.get("day") == day_code]
    return (tt.get("title") or "", day_entries)


def days_for_course(email: str, course_query: str) -> List[str]:
    """Devuelve días (mon..sat) donde aparece una materia que coincide con `course_query`.

    Coincidencia insensible a acentos/caso y tolerante (substring).
    """
    profile = _get_user_profile(email)
    tt = _get_current_timetable(profile)
    if not tt:
        return []
    entries = _list_entries(tt["id"]) 
    qn = _norm_text(course_query)
    found: List[str] = []
    for e in entries:
        name_n = _norm_text(e.get("course_name"))
        if qn and qn in name_n:
            if e.get("day") not in found:
                found.append(e.get("day"))
    return found


def schedule_text_by_params(program: str, semester: int | str, shift: str | None, group: str | None = None) -> Optional[str]:
    """Crea un resumen de horario por parámetros (sin requerir perfil).

    Busca `timetable` vigente por department DASC + program/semester/(shift)/group y
    devuelve un texto ordenado por día y hora.
    """
    db = get_db()
    try:
        q: Dict[str, Any] = {
            "department_code": "DASC",
            "program_code": str(program or "").upper(),
            "semester": int(semester),
            "is_current": True,
        }
        if shift:
            q["shift"] = str(shift).upper()
        if group:
            q["group"] = str(group).upper()
        tt = db["timetable"].find_one(q, {"_id": 1, "title": 1})
        if not tt:
            return None
        items = list(db["timetable_entry"].find({"timetable_id": str(tt["_id"])}, {"_id": 0}).sort([("day", 1), ("start_time", 1)]))
        if not items:
            return None
        # Orden agrupado por día con etiquetas en español
        by_day: Dict[str, List[Dict[str, Any]]] = {}
        for e in items:
            by_day.setdefault(e.get("day"), []).append(e)
        order = ["mon", "tue", "wed", "thu", "fri", "sat"]
        parts: List[str] = [f"Horario vigente: {tt.get('title')}"]
        for d in order:
            if d in by_day:
                label = CODE_TO_SPANISH_DAY.get(d, d).capitalize()
                blocks = "; ".join(_fmt_entry(e) for e in by_day[d])
                parts.append(f"{label}: {blocks}")
        return "\n".join(parts)
    except Exception:
        return None


def schedule_text_for_user(email: str) -> Optional[str]:
    """Resumen textual del horario vigente del usuario (por perfil).

    Devuelve None si no encuentra timetable vigente.
    """
    prof = _get_user_profile(email)
    tt = _get_current_timetable(prof)
    if not tt:
        return None
    db = get_db()
    items = list(db["timetable_entry"].find({"timetable_id": str(tt["id"])}, {"_id": 0}).sort([("day", 1), ("start_time", 1)]))
    if not items:
        return None
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for e in items:
        by_day.setdefault(e.get("day"), []).append(e)
    order = ["mon", "tue", "wed", "thu", "fri", "sat"]
    parts: List[str] = [f"Horario vigente: {tt.get('title')}"]
    for d in order:
        if d in by_day:
            label = CODE_TO_SPANISH_DAY.get(d, d).capitalize()
            blocks = "; ".join(_fmt_entry(e) for e in by_day[d])
            parts.append(f"{label}: {blocks}")
    return "\n".join(parts)


def next_class(email: str, ref: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    # Obtén tz del usuario
    profile = _get_user_profile(email)
    tz = profile.get("tz")
    ref = ref or _now_in_tz(tz)
    title, today = classes_for_day(email, ref)
    if today:
        now_m = ref.hour * 60 + ref.minute
        for e in today:
            if _time_to_minutes(e["end_time"]) > now_m:
                return {**e, "timetable_title": title, "day": _weekday_code(ref)}
    # Si no hay más hoy, probar mañana
    for i in range(1, 7):
        d = ref + timedelta(days=i)
        _, entries = classes_for_day(email, d)
        if entries:
            e = entries[0]
            return {**e, "timetable_title": title, "day": _weekday_code(d)}
    return None


def try_answer_schedule(email: str, question: str) -> Optional[str]:
    """
    Si la pregunta es del tipo horario, devuelve una respuesta lista para el usuario.
    En otro caso, devuelve None y deja que el LLM responda.
    """
    q = (question or "").strip().lower()
    if not q:
        return None

    # Verifica perfil mínimo
    prof = _get_user_profile(email) or {}
    missing: list[str] = []
    # Ya no pedimos nombre para responder el horario
    if not (prof.get("major")):
        missing.append("carrera")
    if not (prof.get("shift")):
        missing.append("turno")
    if not (prof.get("semester")):
        missing.append("semestre")
    if missing:
        return (
            "Para responder con tu horario necesito tu "
            + ", ".join(missing)
            + ". Puedes decírmelos aquí (no se guardarán en tu perfil)."
        )

    intents = {
        "now": any(x in q for x in ["ahorita", "ahora", "en este momento"]),
        "today": "hoy" in q,
        "tomorrow": "mañana" in q or "manana" in q,
    }

    # día explícito (lunes...) prevalece sobre hoy/mañana
    for k, code in SPANISH_DAY_TO_CODE.items():
        if k in q:
            # Busca el próximo k a partir de hoy
            prof = _get_user_profile(email)
            ref = _now_in_tz(prof.get("tz"))
            target_idx = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].index(code)
            for i in range(7):
                d = ref + timedelta(days=i)
                if _weekday_code(d) == code:
                    title, entries = classes_for_day(email, d)
                    if not entries:
                        return f"No tengo bloques para {k.capitalize()} en tu horario actual."
                    items = "; ".join(_fmt_entry(e) for e in entries)
                    return f"{k.capitalize()}: {items}."

    # hoy / mañana / ahora
    prof = _get_user_profile(email)
    now = _now_in_tz(prof.get("tz"))
    if intents["now"]:
        nxt = next_class(email, now)
        if not nxt:
            return "No encuentro clases próximas en tu horario vigente."
        day = CODE_TO_SPANISH_DAY.get(nxt["day"], nxt["day"]).capitalize()
        return f"Próxima clase ({day} {nxt['start_time']}): {nxt['course_name']} en {nxt.get('room_code') or 'Aula por confirmar'}."

    if intents["today"]:
        title, entries = classes_for_day(email, now)
        if not entries:
            return "No tengo clases registradas para hoy en tu horario."
        items = "; ".join(_fmt_entry(e) for e in entries)
        return f"Hoy: {items}."

    if intents["tomorrow"]:
        # Busca el próximo día con clases, evitando domingos y asuetos.
        for i in range(1, 8):
            d = now + timedelta(days=i)
            if _weekday_code(d) == "sun":
                continue
            try:
                if is_holiday(d):
                    continue
            except Exception:
                # Si el calendario no está disponible, no bloqueamos la respuesta.
                pass
            _, entries = classes_for_day(email, d)
            if entries:
                items = "; ".join(_fmt_entry(e) for e in entries)
                day_label = CODE_TO_SPANISH_DAY.get(_weekday_code(d), "").capitalize()
                return f"Próximo día con clases ({day_label}): {items}."
        return "No encuentro un próximo día con clases registradas en tu horario."

    # frases comunes
    if any(x in q for x in [
        "que me toca",
        "qué me toca",
        "que clase me toca",
        "qué clase me toca",
        "materias tengo",
        "clases tengo",
        "que clases tengo",
        "qué clases tengo",
    ]):
        # fallback a "hoy" si no especifican
        title, entries = classes_for_day(email, now)
        if not entries:
            return "No tengo clases registradas para hoy en tu horario."
        items = "; ".join(_fmt_entry(e) for e in entries)
        return f"Hoy: {items}."

    return None


def get_schedule_answer(email: str, when: str, day_name: Optional[str] = None) -> str:
    """
    API estable para el tool de OpenAI.
    - when: "now" | "today" | "tomorrow" | "day"
    - day_name: requerido cuando when == "day" (p.ej., "lunes")
    """
    when = (when or "").strip().lower()
    prof = _get_user_profile(email)
    now = _now_in_tz(prof.get("tz"))

    if when == "now":
        nxt = next_class(email, now)
        if not nxt:
            return "No encuentro clases próximas en tu horario vigente."
        day = CODE_TO_SPANISH_DAY.get(nxt["day"], nxt["day"]).capitalize()
        return f"Próxima clase ({day} {nxt['start_time']}): {nxt['course_name']} en {nxt.get('room_code') or 'Aula por confirmar'}."

    if when == "today":
        day_label = CODE_TO_SPANISH_DAY.get(_weekday_code(now), "Hoy").capitalize()
        _, entries = classes_for_day(email, now)
        if not entries:
            return f"No tengo clases registradas para hoy ({day_label})."
        return f"Hoy ({day_label}): " + "; ".join(_fmt_entry(e) for e in entries)

    if when == "tomorrow":
        # Busca el próximo día hábil con clases, evitando domingos y asuetos registrados
        found_entries: List[Dict[str, Any]] = []
        selected_day: Optional[datetime] = None
        for i in range(1, 8):
            d = now + timedelta(days=i)
            if _weekday_code(d) == "sun":
                continue
            try:
                if is_holiday(d):
                    continue
            except Exception:
                # Si no hay calendario disponible, seguimos sin bloquear la respuesta
                pass
            _, entries = classes_for_day(email, d)
            if entries:
                found_entries = entries
                selected_day = d
                break
        if not found_entries:
            return "No encuentro un próximo día con clases registradas en tu horario."
        day_label = CODE_TO_SPANISH_DAY.get(_weekday_code(selected_day or now), "").capitalize()
        return f"Próximo día con clases ({day_label}): " + "; ".join(_fmt_entry(e) for e in found_entries)

    if when == "day":
        name = (day_name or "").strip().lower()
        code = SPANISH_DAY_TO_CODE.get(name)
        if not code:
            return "Necesito un día válido (lunes a sábado)."
        # busca el próximo día indicado a partir de hoy
        ref = now
        for i in range(7):
            d = ref + timedelta(days=i)
            if _weekday_code(d) == code:
                _, entries = classes_for_day(email, d)
                if not entries:
                    return f"No tengo bloques para {name.capitalize()} en tu horario actual."
                return f"{name.capitalize()}: " + "; ".join(_fmt_entry(e) for e in entries)
        return f"No pude ubicar {name}."

    return "No entendí el momento solicitado del horario."


def get_schedule_payload(email: str, when: str, day_name: Optional[str] = None) -> Dict[str, Any]:
    """Versión estructurada para tool-calling.

    Devuelve un payload con metadatos y entradas en lugar de texto plano.
    """
    when = (when or "").strip().lower()
    profile = _get_user_profile(email)
    now = _now_in_tz(profile.get("tz"))

    def _entry_dict(e: Dict[str, Any], day: str, title: str) -> Dict[str, Any]:
        return {
            "day": day,
            "timetable_title": title,
            "start_time": e.get("start_time"),
            "end_time": e.get("end_time"),
            "course_name": e.get("course_name"),
            "room_code": e.get("room_code"),
            "instructor": e.get("instructor"),
        }

    if when == "now":
        nxt = next_class(email, now)
        if not nxt:
            return {"type": "schedule", "when": "now", "entries": [], "message": "no_upcoming"}
        return {
            "type": "schedule",
            "when": "now",
            "entries": [
                _entry_dict(nxt, nxt.get("day"), nxt.get("timetable_title", "")),
            ],
        }

    if when == "today":
        title, entries = classes_for_day(email, now)
        return {
            "type": "schedule",
            "when": "today",
            "entries": [_entry_dict(e, _weekday_code(now), title) for e in entries],
        }

    if when == "tomorrow":
        for i in range(1, 8):
            d = now + timedelta(days=i)
            if _weekday_code(d) == "sun":
                continue
            try:
                if is_holiday(d):
                    continue
            except Exception:
                pass
            title, entries = classes_for_day(email, d)
            if entries:
                return {
                    "type": "schedule",
                    "when": "tomorrow",
                    "selected_date": d.strftime("%Y-%m-%d"),
                    "day_label_es": CODE_TO_SPANISH_DAY.get(_weekday_code(d), ""),
                    "entries": [_entry_dict(e, _weekday_code(d), title) for e in entries],
                }
        return {"type": "schedule", "when": "tomorrow", "entries": []}

def get_current_timetable_for_user(email: str) -> Optional[Dict[str, Any]]:
    """Helper público para obtener el timetable vigente del usuario.

    Devuelve el documento con campo `id` (str) si existe.
    """
    profile = _get_user_profile(email)
    return _get_current_timetable(profile)

    if when == "day":
        name = (day_name or "").strip().lower()
        code = SPANISH_DAY_TO_CODE.get(name)
        if not code:
            return {"type": "schedule", "when": "day", "error": "invalid_day"}
        # Busca el próximo día indicado a partir de hoy
        ref = now
        for i in range(7):
            d = ref + timedelta(days=i)
            if _weekday_code(d) == code:
                title, entries = classes_for_day(email, d)
                return {
                    "type": "schedule",
                    "when": "day",
                    "day_name": name,
                    "entries": [_entry_dict(e, code, title) for e in entries],
                }
        return {"type": "schedule", "when": "day", "day_name": name, "entries": []}

    return {"type": "schedule", "when": when or "", "error": "unknown_when"}
