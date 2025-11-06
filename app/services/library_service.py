"""Servicio de búsqueda/respuesta para documentos institucionales.

Incluye utilidades para localizar assets (PDFs) en `library_asset`.
"""
from __future__ import annotations

from typing import Optional, Dict

from app.repositories.library_repo import search_documents
from app.repositories.library_asset_repo import search_assets


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


def find_asset_pdf_url(query: str) -> Optional[Dict[str, str]]:
    """Busca en `library_asset` por título/tags y devuelve el mejor match con su URL pública.

    Retorna dict con: {"title": str, "url": str} o None si no encuentra.
    """
    items = search_assets(query, limit=5)
    if not items:
        return None
    # Prioriza elementos con file_url y mime_type PDF
    pdfs = [i for i in items if i.get("file_url") and str(i.get("mime_type", "")).lower().endswith("pdf")]
    best = pdfs[0] if pdfs else (items[0] if items and items[0].get("file_url") else None)
    if not best:
        return None
    return {"title": best.get("title") or "", "url": best.get("file_url")}


def find_calendar_pdf_url() -> Optional[Dict[str, str]]:
    """Heurística para ubicar el calendario escolar en assets.

    Intenta varias consultas comunes y devuelve el primer match con URL.
    """
    queries = [
        "calendario escolar 2025",
        "calendario 2025",
        "calendario escolar",
        "calendario uabcs",
    ]
    for q in queries:
        hit = find_asset_pdf_url(q)
        if hit and hit.get("url"):
            return hit
    return None
