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

        hs = list(
            db["horarios"].find(
                {"usuario_correo": user_email},
                {"_id": 0}
            )
        )

        # Catálogo de materias (recorta a 8 para no inflar prompts)
        ms = list(
            db["materias"].find(
                {},
                {"_id": 0}
            )
        )

        partes: list[str] = []

        if u:
            prof = (u.get("profile") or {})
            partes.append(
                f"Alumno: {prof.get('full_name')} | Carrera: {prof.get('major')} | Semestre: {prof.get('semester')}"
            )

        if hs:
            horarios_txt = "; ".join(
                f"{h['materia_codigo']} {h['dia']} {h['hora_inicio']}-{h['hora_fin']}"
                for h in hs
            )
            partes.append(f"Horarios del alumno: {horarios_txt}")

        if ms:
            materias_txt = "; ".join(
                f"{m['codigo']}:{m['nombre']} ({m['profesor']}, {m['salon']})"
                for m in ms[:8]
            )
            partes.append(f"Materias catálogo (máx. 8): {materias_txt}")

        return "\n".join(partes) if partes else "Sin datos académicos del alumno aún."
    except Exception:
        return "No se pudo leer contexto de la BD."
