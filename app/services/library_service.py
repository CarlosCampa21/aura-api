"""Servicio de búsqueda/respuesta para documentos institucionales."""
from __future__ import annotations

from typing import Optional

from app.repositories.library_repo import search_documents


def search_document_answer(query: str) -> Optional[str]:
    items = search_documents(query, limit=3)
    if not items:
        return None
    # Formatea una respuesta breve con el mejor match y alternativas
    best = items[0]
    out = [
        f"Encontré esto: {best['title']}",
    ]
    if best.get("file_url"):
        out.append(f"Descargar/Ver: {best['file_url']}")
    if len(items) > 1:
        alts = ", ".join(i["title"] for i in items[1:])
        out.append(f"También tengo: {alts}.")
    return "\n".join(out)

