#!/usr/bin/env python3
"""
Sincroniza días de asueto desde el documento de calendario escolar (RAG)
al modelo determinista `calendar_holiday` usado por el servicio de horarios.

Estrategia:
  - Localiza un `library_doc` por --doc-id o --query (p.ej. "calendario escolar 2025").
  - Descarga el archivo (MD/PDF/TXT) desde `url` pública de R2.
  - Extrae texto con los extractores existentes.
  - Identifica la sección "Días de asueto" (si existe) y parsea fechas del tipo
      "17 de marzo de 2025" (insensible a mayúsculas/acentos).
  - Inserta/actualiza cada fecha en `calendar_holiday` con `reason` = línea origen.

Uso:
  PYTHONPATH=. python3 scripts/sync_holidays_from_calendar.py --query "calendario escolar 2025"
  PYTHONPATH=. python3 scripts/sync_holidays_from_calendar.py --doc-id <id>
"""
from __future__ import annotations

import argparse
import re
from typing import Dict, List, Tuple

import requests

from app.infrastructure.db.mongo import init_mongo, get_db
from app.infrastructure.db.bootstrap import ensure_collections
from app.repositories.library_repo import get_document, search_documents
from app.infrastructure.text import extractors


MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


DATE_RE = re.compile(
    r"(?i)(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})"
)


def _http_get(url: str) -> bytes:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content


def _extract_text(data: bytes, content_type: str, url: str) -> str:
    ct = (content_type or "").lower()
    u = (url or "").lower()
    if ct.startswith("text/markdown") or u.endswith(".md"):
        return extractors.extract_text_from_md(data)
    if ct.startswith("application/pdf") or u.endswith(".pdf"):
        txt, _ = extractors.extract_text_from_pdf(data)
        return txt
    if ct.startswith("text/plain") or u.endswith(".txt"):
        return extractors.extract_text_from_txt(data)
    return extractors.extract_text_from_txt(data)


def _find_holiday_section(text: str) -> str:
    # Busca bloque desde heading "Días de asueto" hasta el siguiente heading
    m = re.search(r"(?is)^\s*##\s*d[ií]as\s+de\s+asueto.*?(?=^\s*##\s|\Z)", text, flags=re.MULTILINE)
    if m:
        return m.group(0)
    # Fallback: todo el texto si no hay heading claro
    return text


def _parse_dates_with_reason(section: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for line in section.splitlines():
        line = line.strip()
        if not line:
            continue
        for m in DATE_RE.finditer(line):
            d, mon, y = m.groups()
            y_i = int(y)
            m_i = MONTHS.get(mon.lower(), 0)
            if m_i <= 0:
                continue
            day_i = int(d)
            date_iso = f"{y_i:04d}-{m_i:02d}-{day_i:02d}"
            out.append((date_iso, line))
    # Dedup por fecha conservando primer motivo
    seen = set()
    uniq: List[Tuple[str, str]] = []
    for di, reason in out:
        if di not in seen:
            seen.add(di)
            uniq.append((di, reason))
    return uniq


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-id", default=None)
    ap.add_argument("--query", default=None, help="Texto para localizar library_doc (ej. 'calendario escolar 2025')")
    args = ap.parse_args()

    if not args.doc_id and not args.query:
        raise SystemExit("Especifica --doc-id o --query")

    init_mongo()
    ensure_collections()
    db = get_db()

    doc = None
    if args.doc_id:
        doc = get_document(args.doc_id)
    else:
        hits = search_documents(args.query or "calendario escolar", limit=3)
        for h in hits:
            if h.get("file_url"):
                doc = get_document(h["id"])  # obtener content_type/url completas
                break
    if not doc or not doc.get("file_url"):
        raise SystemExit("No se encontró un library_doc con URL pública")

    data = _http_get(doc["file_url"])  # URL pública en R2
    text = _extract_text(data, str(doc.get("content_type") or ""), str(doc.get("file_url") or ""))
    section = _find_holiday_section(text)
    pairs = _parse_dates_with_reason(section)
    if not pairs:
        print("No se detectaron fechas de asueto en el documento.")
        return

    # Upsert por fecha
    n_up = 0
    for date_iso, reason in pairs:
        db["calendar_holiday"].update_one(
            {"date": date_iso},
            {"$set": {"date": date_iso, "reason": reason}},
            upsert=True,
        )
        n_up += 1
    print(f"Holidays upserted: {n_up}")


if __name__ == "__main__":
    main()

