# app/services/context_builder.py
from app.infrastructure.db.mongo import get_db

def build_academic_context(user_email: str) -> str:
    """
    Arma un mini-contexto con datos del alumno desde Mongo para enriquecer la respuesta.
    (Ligero para no enviar demasiados tokens.)
    """
    try:
        db = get_db()

        u = db["user"].find_one({"email": user_email}, {"_id": 0})

        # Deriva contexto de timetable/timetable_entry (nuevo modelo)
        prof = (u or {}).get("profile") or {}
        program_code = (prof.get("major") or "").upper() or None
        semester = prof.get("semester") or None
        shift = prof.get("shift") or None  # "TM"/"TV" si existe
        group = prof.get("group") or None

        timetable = None
        if program_code and semester:
            q = {
                "department_code": "DASC",
                "program_code": program_code,
                "semester": semester,
                "period_code": {"$exists": True},
                "is_current": True,
            }
            if shift:
                q["shift"] = shift
            if group:
                q["group"] = group
            timetable = db["timetable"].find_one(q, {"_id": 1, "title": 1})

        entries = []
        if timetable:
            entries = list(
                db["timetable_entry"].find(
                    {"timetable_id": str(timetable.get("_id"))},
                    {"_id": 0}
                ).sort([("day", 1), ("start_time", 1)])
            )

        partes: list[str] = []

        if u:
            prof = (u.get("profile") or {})
            partes.append(
                f"Alumno: {prof.get('full_name')} | Carrera: {prof.get('major')} | Semestre: {prof.get('semester')}"
            )

        if timetable:
            partes.append(f"Horario vigente: {timetable.get('title')}")

        if entries:
            bloques = "; ".join(
                f"{e['day']} {e['start_time']}-{e['end_time']} {e['course_name']} {e.get('room_code') or ''}".strip()
                for e in entries[:12]
            )
            partes.append(f"Bloques (máx.12): {bloques}")

        return "\n".join(partes) if partes else "Sin datos académicos del alumno aún."
    except Exception:
        return "No se pudo leer contexto de la BD."
