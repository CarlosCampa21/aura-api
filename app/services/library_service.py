"""Servicio de búsqueda/respuesta para documentos institucionales.

Incluye utilidades para localizar assets (PDFs) en `library_asset`.
"""
from __future__ import annotations

from typing import Optional, Dict

from app.repositories.library_repo import search_documents, get_document
from app.repositories.library_asset_repo import search_assets
from app.services.schedule_service import get_current_timetable_for_user
from app.infrastructure.db.mongo import get_db
from bson import ObjectId


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


def find_calendar_image_url() -> Optional[Dict[str, str]]:
    """Localiza una imagen/miniatura del calendario escolar si existe en assets.

    Busca por consultas comunes y prioriza mime_type image/*. Devuelve {title,url}.
    """
    queries = [
        "calendario escolar 2025",
        "calendario 2025",
        "calendario escolar",
        "calendario uabcs",
    ]
    try:
        for q in queries:
            items = search_assets(q, limit=10)
            imgs = [i for i in items if (i.get("file_url") and str(i.get("mime_type", "" )).lower().startswith("image/"))]
            if imgs:
                return {"title": imgs[0].get("title") or "Calendario escolar", "url": imgs[0].get("file_url")}
    except Exception:
        return None
    return None


def find_schedule_image_for_user(user_email: str) -> Optional[Dict[str, str]]:
    """Intenta localizar una imagen de horario para el timetable vigente del usuario.

    Heurística: construye consultas por título/tags con "horario <program> <semester> <shift> <period>".
    Devuelve {title,url} o None.
    """
    try:
        tt = get_current_timetable_for_user(user_email)
        if not tt:
            return None
        program = (tt.get("program_code") or "").upper()
        sem = str(tt.get("semester") or "")
        shift = str(tt.get("shift") or "").upper()
        period = str(tt.get("period_code") or "")
        # 0) Intentar por doc_ref si existe un library_doc con el mismo título
        try:
            title_guess = tt.get("title") or f"Horario {program} {sem} {shift} {period}".strip()
            if title_guess:
                docs = search_documents(title_guess, limit=1)
                if docs:
                    did = docs[0].get("id")
                    if did:
                        db = get_db()
                        rows = list(db["library_asset"].find({"doc_ref": ObjectId(did), "enabled": True}))
                        imgs = [r for r in rows if str(r.get("mime_type","" )).lower().startswith("image/") and r.get("url")]
                        if imgs:
                            return {"title": imgs[0].get("title") or title_guess, "url": imgs[0].get("url")}
        except Exception:
            pass

        # 1) Construye múltiples consultas robustas
        queries = [
            " ".join([p for p in ["horario", program, sem, shift, period] if p]),
            " ".join([p for p in ["horario", program, sem, shift] if p]),
            " ".join([p for p in ["horario", program, sem] if p]),
            (tt.get("title") or ""),
        ]
        # 2) Intenta primero imágenes explícitas
        for q in queries + [q + " imagen" for q in queries]:
            if not q.strip():
                continue
            items = search_assets(q, limit=10)
            imgs = [
                i for i in items
                if (i.get("file_url") and str(i.get("mime_type", "")).lower().startswith("image/"))
            ]
            if imgs:
                return {"title": imgs[0].get("title") or "", "url": imgs[0].get("file_url")}
        # 3) Como último recurso, acepta un PDF si no hay imagen
        for q in queries:
            if not q.strip():
                continue
            hit = find_asset_pdf_url(q)
            if hit:
                return hit
        return None
    except Exception:
        return None


def find_schedule_image_by_params(program: str, semester: int | str, shift: str | None, period: str | None = None) -> Optional[Dict[str, str]]:
    """Localiza una imagen de horario usando parámetros explícitos.

    Busca en `library_asset` por título/tags. Prioriza mime_type image/*.
    """
    try:
        prog = (program or "").upper()
        sem = str(semester or "").strip()
        sh = (shift or "").upper().strip()
        per = str(period or "").strip()
        q = " ".join([p for p in ["horario", prog, sem, sh, per] if p])
        items = search_assets(q, limit=10)
        imgs = [i for i in items if (i.get("file_url") and str(i.get("mime_type","" )).lower().startswith("image/"))]
        if imgs:
            return {"title": imgs[0].get("title") or "", "url": imgs[0].get("file_url")}
        return None
    except Exception:
        return None


def find_schedule_image_by_title(title: str) -> Optional[Dict[str, str]]:
    """Localiza una imagen de horario buscando por el título completo (o parte de él).

    Útil cuando el turno previo ya mostró el horario en texto con "Horario vigente: <title>".
    """
    try:
        q = (title or "").strip()
        if not q:
            return None
        # 1) doc_ref preferente
        try:
            docs = search_documents(q, limit=1)
            if docs:
                did = docs[0].get("id")
                if did:
                    db = get_db()
                    rows = list(db["library_asset"].find({"doc_ref": ObjectId(did), "enabled": True}))
                    imgs = [r for r in rows if str(r.get("mime_type","" )).lower().startswith("image/") and r.get("url")]
                    if imgs:
                        return {"title": imgs[0].get("title") or q, "url": imgs[0].get("url")}
        except Exception:
            pass
        # 2) búsqueda directa en assets por título
        items = search_assets(q, limit=10)
        imgs = [i for i in items if (i.get("file_url") and str(i.get("mime_type","" )).lower().startswith("image/"))]
        if imgs:
            return {"title": imgs[0].get("title") or q, "url": imgs[0].get("file_url")}
        return None
    except Exception:
        return None
