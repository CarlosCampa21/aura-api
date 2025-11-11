#!/usr/bin/env python
"""
Importa un horario desde una tabla Markdown a las colecciones
`timetable` y `timetable_entry`.

Pensado para tablas con columnas: Hora | Lunes | Martes | Miércoles | Jueves | Viernes (opcional Sábado)
con celdas tipo "**Materia**<br>Docente<br>Aula". Las celdas con guiones/ vacío se omiten.

Uso (ejemplo IDS 9 TM 2025-II):
  PYTHONPATH=. python scripts/import_timetable_from_md.py \
    --file data/rag/Horario_Desarrollo_Software_9_MT_2025-II.md \
    --department DASC --program IDS --semester 9 --group A --period 2025-II --shift TM \
    --title "IDS 9 TM Grupo A 2025-II" --publish

El script asegura catálogos mínimos (department/program/period), inserta/actualiza un
`timetable` y reemplaza sus `timetable_entry` según el archivo.
"""
from __future__ import annotations

import argparse
import re
from typing import Dict, List, Tuple

from app.infrastructure.db.mongo import init_mongo, get_db
from app.infrastructure.db.bootstrap import ensure_collections
from app.repositories.academics_catalog_repo import (
    insert_department,
    insert_program,
    insert_period,
)
from app.repositories.academics_timetables_repo import insert_timetable, publish_timetable
from app.repositories.academics_entries_repo import insert_entries_bulk


DAY_ORDER = ["lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado"]
DAY_TO_CODE = {
    "lunes": "mon",
    "martes": "tue",
    "miercoles": "wed",
    "miércoles": "wed",
    "jueves": "thu",
    "viernes": "fri",
    "sabado": "sat",
    "sábado": "sat",
}


TIME_RE = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})\s*[–\-]\s*(\d{1,2})\s*[:：]\s*(\d{2})")


def _norm_time(h: str, m: str) -> str:
    h_i = int(h)
    m_i = int(m)
    return f"{h_i:02d}:{m_i:02d}"


def _parse_time_range(s: str) -> Tuple[str, str] | None:
    m = TIME_RE.search(s.replace("—", "-").replace("–", "-"))
    if not m:
        return None
    return _norm_time(m.group(1), m.group(2)), _norm_time(m.group(3), m.group(4))


def _split_table(md: str) -> Tuple[List[str], List[List[str]]]:
    """Devuelve (headers, rows) de la primera tabla Markdown encontrada."""
    lines = [l.rstrip() for l in md.splitlines()]
    start = -1
    for i, l in enumerate(lines):
        if l.strip().startswith("|") and "|" in l.strip("|"):
            # busca separador en la siguiente línea
            if i + 1 < len(lines) and set(lines[i + 1].strip().strip("|").replace(" ", "").replace(":", "")).issubset({"-", "|"}):
                start = i
                break
    if start < 0:
        return [], []
    header = [c.strip() for c in lines[start].strip().strip("|").split("|")]
    rows: List[List[str]] = []
    i = start + 2
    while i < len(lines) and lines[i].strip().startswith("|"):
        row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        rows.append(row)
        i += 1
    return header, rows


def _cell_to_fields(cell: str) -> Tuple[str, str | None, str | None]:
    """Extrae (materia, docente, aula) de una celda HTML-like con <br>."""
    raw = cell.strip()
    if not raw or raw in {"-", "—", "— ", "—", "—", "—"}:
        return "", None, None
    # quita **bold** y HTML simple
    txt = re.sub(r"\*\*([^*]+)\*\*", r"\1", raw)
    parts = [p.strip() for p in re.split(r"<br\s*/?>", txt, flags=re.IGNORECASE) if p.strip()]
    materia = parts[0] if parts else ""
    docente = parts[1] if len(parts) > 1 else None
    aula = parts[2] if len(parts) > 2 else None
    # normaliza guiones largos en vacío
    if materia in {"-", "—"}:
        materia = ""
    return materia, docente, aula


def parse_markdown_timetable(md: str) -> List[Dict[str, str]]:
    """Convierte tabla Markdown a lista de entradas con llaves: day,start_time,end_time,course_name,instructor,room_code."""
    headers, rows = _split_table(md)
    if not headers or not rows:
        return []
    # Mapea columnas de días
    day_cols: List[Tuple[int, str]] = []
    for idx, h in enumerate(headers):
        h_low = h.lower()
        if h_low in {"hora", "horario"}:
            continue
        # encuentra día conocido
        for d in DAY_ORDER:
            if d in h_low:
                day_cols.append((idx, DAY_TO_CODE[d]))
                break
    entries: List[Dict[str, str]] = []
    for row in rows:
        if not row:
            continue
        tr = _parse_time_range(row[0]) if len(row) > 0 else None
        if not tr:
            continue
        start, end = tr
        for idx, day_code in day_cols:
            if idx >= len(row):
                continue
            materia, docente, aula = _cell_to_fields(row[idx])
            if not materia:
                continue
            entries.append({
                "day": day_code,
                "start_time": start,
                "end_time": end,
                "course_name": materia,
                "instructor": docente,
                "room_code": (aula or None),
                "modality": "class",
            })
    # Orden por día/hora para estabilidad
    day_rank = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
    entries.sort(key=lambda e: (day_rank.get(e["day"], 9), e["start_time"]))
    return entries


def main() -> None:
    ap = argparse.ArgumentParser(description="Importa horario desde Markdown a timetable/timetable_entry")
    ap.add_argument("--file", required=True, help="Ruta al archivo .md con la tabla del horario")
    ap.add_argument("--department", default="DASC")
    ap.add_argument("--program", required=True, help="Código de programa, p.ej. IDS")
    ap.add_argument("--semester", required=True, type=int)
    ap.add_argument("--group", required=True)
    ap.add_argument("--period", required=True, help="Código de periodo, p.ej. 2025-II")
    ap.add_argument("--shift", choices=["TM", "TV"], required=False)
    ap.add_argument("--title", default=None)
    ap.add_argument("--notes", default=None)
    ap.add_argument("--version", type=int, default=1, help="Versión del horario (útil para módulos). Por defecto 1")
    ap.add_argument("--publish", action="store_true", help="Marcar como vigente y desmarcar otros de la misma combinación")
    args = ap.parse_args()

    init_mongo()
    ensure_collections()
    db = get_db()

    # Asegura catálogos mínimos
    if not db["department"].find_one({"code": args.department}):
        insert_department({"code": args.department, "name": args.department})
    if not db["program"].find_one({"department_code": args.department, "code": args.program}):
        insert_program({"department_code": args.department, "code": args.program, "name": args.program})
    if not db["period"].find_one({"code": args.period}):
        insert_period({"code": args.period, "year": 0, "term": args.period, "status": "active"})

    md = open(args.file, "r", encoding="utf-8").read()
    entries = parse_markdown_timetable(md)
    if not entries:
        raise SystemExit("No se pudieron extraer entradas desde el Markdown")

    combo = {
        "department_code": args.department,
        "program_code": args.program,
        "semester": int(args.semester),
        "group": str(args.group),
        "period_code": args.period,
        "shift": args.shift,
        "version": int(args.version),
        "title": args.title or f"{args.program} {args.semester} {args.shift or ''} Grupo {args.group} {args.period}".strip(),
        "notes": args.notes,
    }

    existing = db["timetable"].find_one({
        "department_code": combo["department_code"],
        "program_code": combo["program_code"],
        "semester": combo["semester"],
        "group": combo["group"],
        "period_code": combo["period_code"],
        "version": combo["version"],
        **({"shift": combo["shift"]} if combo.get("shift") else {}),
    })
    if existing:
        timetable_id = str(existing["_id"])
    else:
        timetable_id = insert_timetable(combo)

    # Reemplaza entradas previas
    db["timetable_entry"].delete_many({"timetable_id": timetable_id})
    inserted = insert_entries_bulk(timetable_id, entries)

    if args.publish:
        publish_timetable(timetable_id)

    print(f"Timetable {timetable_id} actualizado; entradas insertadas: {inserted}")


if __name__ == "__main__":
    main()
