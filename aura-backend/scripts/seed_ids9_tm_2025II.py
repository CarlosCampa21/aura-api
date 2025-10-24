#!/usr/bin/env python
"""
Seed: IDS 9° semestre, turno matutino (TM), periodo 2025-II

Inserta catálogos mínimos, crea un timetable is_current y registra
entradas SOLO del bloque matutino (07:00-11:30) según la imagen.

Ejecución sugerida desde repo Back-Aura/:
  PYTHONPATH=aura-backend python aura-backend/scripts/seed_ids9_tm_2025II.py
"""
from __future__ import annotations

from typing import List, Dict

from app.infrastructure.db.mongo import init_mongo, get_db
from app.infrastructure.db.bootstrap import ensure_collections
from app.repositories.academics_catalog_repo import (
    insert_department,
    insert_program,
    insert_period,
)
from app.repositories.academics_timetables_repo import (
    insert_timetable,
    publish_timetable,
)
from app.repositories.academics_entries_repo import insert_entries_bulk


def upsert_department(code: str, name: str, campus: str | None = None):
    db = get_db()
    if not db["department"].find_one({"code": code}):
        insert_department({"code": code, "name": name, "campus": campus})


def upsert_program(department_code: str, code: str, name: str):
    db = get_db()
    if not db["program"].find_one({"department_code": department_code, "code": code}):
        insert_program({"department_code": department_code, "code": code, "name": name})


def upsert_period(code: str, year: int, term: str):
    db = get_db()
    if not db["period"].find_one({"code": code}):
        insert_period({"code": code, "year": year, "term": term, "status": "active"})


def main() -> None:
    init_mongo()
    ensure_collections()
    db = get_db()

    # Catálogos mínimos
    upsert_department("DASC", "Depto. Acad. de Sistemas Computacionales")
    upsert_program("DASC", "IDS", "Ingeniería en Desarrollo de Software")
    upsert_period("2025-II", 2025, "II")

    # Timetable cabecera (grupo A, TM)
    combo = {
        "department_code": "DASC",
        "program_code": "IDS",
        "semester": 9,
        "group": "A",
        "period_code": "2025-II",
        "shift": "TM",
        "title": "IDS 9 TM Grupo A 2025-II",
        "notes": "Seed matutino basado en imagen compartida",
    }

    existing = db["timetable"].find_one({
        "department_code": combo["department_code"],
        "program_code": combo["program_code"],
        "semester": combo["semester"],
        "group": combo["group"],
        "period_code": combo["period_code"],
        "shift": combo["shift"],
    })

    if existing:
        timetable_id = str(existing["_id"])
    else:
        timetable_id = insert_timetable(combo)

    # Publica como vigente
    publish_timetable(timetable_id)

    # Limpia entradas previas del mismo timetable para evitar duplicados
    db["timetable_entry"].delete_many({"timetable_id": timetable_id})

    # Entradas (solo mañana)
    E: List[Dict] = []
    def add(day: str, start: str, end: str, name: str, teacher: str | None = None, room: str | None = "VIRTUAL", module: str | None = None):
        E.append({
            "timetable_id": timetable_id,
            "day": day,
            "start_time": start,
            "end_time": end,
            "course_name": name,
            "instructor": teacher,
            "room_code": room,
            "modality": "class",
            "module": module,
        })

    # Lunes (Lu)
    add("mon", "07:00", "08:30", "Prácticas Profesionales", "Alejandro Leyva Carrillo")
    add("mon", "08:30", "10:00", "Optativa V (Tec. Desarr.)", "Nelson Higuera", module="Tec. de Des.")
    # 10:00-11:30: vacío según imagen

    # Martes (Ma)
    add("tue", "07:00", "08:30", "Prácticas Profesionales", "Alejandro Leyva Carrillo")
    add("tue", "08:30", "10:00", "Desarrollo Sustentable", "Rosa Isela Hirales Cota")
    add("tue", "10:00", "11:30", "Desarrollo de un Proyectos de Software", "Mónica Carreño")

    # Miércoles (Mi)
    add("wed", "07:00", "08:30", "Optativa V (Tec. Desarr.)", "Nelson Higuera", module="Tec. de Des.")
    add("wed", "08:30", "10:00", "Desarrollo Sustentable", "Rosa Isela Hirales Cota")
    add("wed", "10:00", "11:30", "Optativa V (OPGS)", None, module="Sist. Intelig.")

    # Jueves (Ju)
    add("thu", "07:00", "08:30", "Prácticas Profesionales", "Alejandro Leyva Carrillo")
    add("thu", "08:30", "10:00", "Optativa V (OPGS)", None, module="Sist. Intelig.")
    add("thu", "10:00", "11:30", "Desarrollo de un Proyectos de Software", "Mónica Carreño")

    # Viernes (Vi)
    add("fri", "07:00", "08:30", "Prácticas Profesionales", "Alejandro Leyva Carrillo")
    add("fri", "08:30", "10:00", "Prácticas Profesionales", "Alejandro Leyva Carrillo")
    add("fri", "10:00", "11:30", "Desarrollo de un Proyectos de Software", "Mónica Carreño")

    inserted = insert_entries_bulk(timetable_id, E)
    print(f"Timetable {timetable_id} publicado; entradas insertadas: {inserted}")


if __name__ == "__main__":
    main()

