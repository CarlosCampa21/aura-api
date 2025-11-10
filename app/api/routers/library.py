"""API de documentos institucionales.

Permite:
- Buscar y obtener metadatos (usa URLs públicas en R2)
- Subir un archivo (PDF/imagen) a R2 y registrar sus metadatos
"""
from __future__ import annotations

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form, Body
from fastapi.responses import RedirectResponse

from app.repositories.library_repo import get_document, insert_document, update_document_tags
from app.repositories.library_asset_repo import (
    search_assets,
    get_asset,
    insert_asset,
    update_asset_tags as repo_update_asset_tags,
)
from app.repositories.files_repo_r2 import upload_uploadfile_to_r2
from app.infrastructure.storage import r2 as r2_storage


router = APIRouter(prefix="/library", tags=["Library"])


def _split_csv(s: Optional[str]) -> List[str]:
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def _parse_json_obj(s: Optional[str]) -> Dict[str, Any]:
    """Parsea un JSON de objeto enviado como string en form-data.

    Si está vacío o inválido, devuelve {} sin lanzar excepción para no romper el upload.
    """
    if not s:
        return {}
    try:
        import json
        data = json.loads(s)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def _upload_r2_by_type(
    *,
    file: UploadFile,
    type_: str,
    title: Optional[str],
    tags: Optional[str],
    aliases: Optional[str] = None,
    department: Optional[str] = None,
    program: Optional[str] = None,
    campus: Optional[str] = None,
    prefix: Optional[str] = None,
    source_is_pdf: Optional[bool] = False,
    metadata: Optional[str] = None,
    alt: Optional[str] = None,
):
    ctype = (file.content_type or "").lower()

    type_norm = (type_ or '').strip().lower()
    if type_norm not in {"media", "docs", "rag"}:
        raise HTTPException(status_code=400, detail="type inválido. Use: media | docs | rag")

    allowed_media = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"}
    allowed_docs = {
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/csv",
        # Microsoft Word (legacy .doc)
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }

    if type_norm == "media":
        if ctype not in allowed_media:
            raise HTTPException(status_code=415, detail=f"Tipo no permitido para media: {ctype}")
        pf = prefix.strip() if (prefix and prefix.strip()) else "library/media/"
        if not pf.startswith("library/media/"):
            raise HTTPException(status_code=400, detail="Prefijo inválido para media; use library/media/")
        if not pf.endswith("/"):
            pf += "/"
        url = await upload_uploadfile_to_r2(file, prefix=pf)
        meta: Dict[str, Any] = {"aliases": _split_csv(aliases) if aliases else []}
        # Merge de metadata opcional + alt como campo de meta
        meta_extra = _parse_json_obj(metadata)
        if alt:
            meta_extra.setdefault("alt", alt)
        if meta_extra:
            meta.update(meta_extra)
        asset = {
            "title": title or (file.filename or "Imagen"),
            "tags": _split_csv(tags),
            "mime_type": ctype,
            "url": url,
            "enabled": True,
            "downloadable": True,
            "version": 1,
            "meta": meta,
        }
        asset_id = insert_asset(asset)
        return {"message": "ok", "id": asset_id, "title": asset["title"], "url": url}

    if type_norm == "docs":
        if ctype not in allowed_docs:
            raise HTTPException(status_code=415, detail=f"Tipo no permitido para docs: {ctype}")
        pf = prefix.strip() if (prefix and prefix.strip()) else "library/docs/"
        if not pf.startswith("library/docs/"):
            raise HTTPException(status_code=400, detail="Prefijo inválido para docs; use library/docs/")
        if not pf.endswith("/"):
            pf += "/"
        url = await upload_uploadfile_to_r2(file, prefix=pf)
        meta: Dict[str, Any] = {
            "aliases": _split_csv(aliases) if aliases else [],
            "department": department,
            "program": program,
            "campus": campus,
        }
        meta_extra = _parse_json_obj(metadata)
        if alt:
            meta_extra.setdefault("alt", alt)
        if meta_extra:
            meta.update(meta_extra)
        asset = {
            "title": title or (file.filename or "Documento"),
            "tags": _split_csv(tags),
            "mime_type": ctype,
            "url": url,
            "enabled": True,
            "downloadable": True,
            "version": 1,
            "meta": meta,
        }
        asset_id = insert_asset(asset)
        return {"message": "ok", "id": asset_id, "title": asset["title"], "url": url}

    # rag
    if ctype not in allowed_docs:
        raise HTTPException(status_code=415, detail=f"Tipo no permitido para rag: {ctype}")
    pf = prefix.strip() if (prefix and prefix.strip()) else "library/rag/"
    if not pf.startswith("library/rag/"):
        raise HTTPException(status_code=400, detail="Prefijo inválido para rag; use library/rag/")
    if not pf.endswith("/"):
        pf += "/"
    url = await upload_uploadfile_to_r2(file, prefix=pf)
    doc = {
        "title": title or (file.filename or "Documento RAG"),
        "kind": "rag",
        "content_type": ctype,
        "url": url,
        "source_pdf_url": url if source_is_pdf else None,
        "tags": _split_csv(tags),
        "enabled": True,
        "version": 1,
        "ingest": {
            "embed_model": "text-embedding-3-small",
            "chunk_size": 800,
            "chunk_overlap": 160,
            "last_ingested_at": None,
            "status": "pending",
        },
    }
    doc_id = insert_document(doc)
    return {"message": "ok", "id": doc_id, "title": doc["title"], "url": url}


@router.get("/search", response_model=dict, summary="Buscar assets descargables (library_asset)")
def search(q: str = Query(..., min_length=2), limit: int = Query(5, ge=1, le=20)):
    try:
        items = search_assets(q, limit=limit)
        return {"results": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo buscar: {e}")


@router.get("/assets/search", response_model=dict, summary="Buscar assets descargables (library_asset)")
def search_assets_api(q: str = Query(..., min_length=2), limit: int = Query(5, ge=1, le=20)):
    try:
        items = search_assets(q, limit=limit)
        return {"results": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo buscar: {e}")


@router.post("/upload", response_model=dict, summary="Subir a R2 por tipo (media/docs/rag)")
async def upload_asset(
    file: UploadFile = File(...),
    type: str = Form(..., description="media | docs | rag"),
    title: Optional[str] = Form(default=None),
    aliases: Optional[str] = Form(default=None, description="Lista separada por comas"),
    tags: Optional[str] = Form(default=None, description="Lista separada por comas"),
    department: Optional[str] = Form(default=None),
    program: Optional[str] = Form(default=None),
    campus: Optional[str] = Form(default=None),
    metadata: Optional[str] = Form(default=None, description="JSON opcional con metadatos adicionales"),
    alt: Optional[str] = Form(default=None, description="Texto alternativo/descripcion corta"),
    prefix: Optional[str] = Form(default=None, description="Prefijo en R2 (opcional). Se valida por tipo."),
    source_is_pdf: Optional[bool] = Form(default=False, description="Sólo para type=rag: copiar URL a source_pdf_url"),
):
    try:
        return await _upload_r2_by_type(
            file=file,
            type_=type,
            title=title,
            tags=tags,
            aliases=aliases,
            department=department,
            program=program,
            campus=campus,
            prefix=prefix,
            source_is_pdf=source_is_pdf,
            metadata=metadata,
            alt=alt,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo subir el asset: {e}")


@router.post("/media/upload", response_model=dict, summary="Subir imagen (R2 → library_asset en library/media)")
async def upload_media(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(default=None, description="Lista separada por comas"),
):
    try:
        return await _upload_r2_by_type(file=file, type_="media", title=title, tags=tags)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo subir la imagen: {e}")


@router.post("/docs/upload", response_model=dict, summary="Subir documento (R2 → library_asset en library/docs)")
async def upload_docs(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(default=None, description="Lista separada por comas"),
):
    try:
        return await _upload_r2_by_type(file=file, type_="docs", title=title, tags=tags)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo subir el documento: {e}")


@router.get("/debug-r2", response_model=dict, summary="Diagnóstico de conexión a R2")
def debug_r2():
    try:
        s3 = r2_storage.get_s3_client()
        bucket = r2_storage.settings.r2_bucket or "(not set)"
        # HeadBucket para validar credenciales/endpoint/firma
        ok = True
        err = None
        try:
            s3.head_bucket(Bucket=bucket)
        except Exception as e:  # pragma: no cover
            ok = False
            err = str(e)
        return {
            "endpoint": r2_storage._endpoint_url(),
            "public_base_url": r2_storage.public_base_url(),
            "bucket": bucket,
            "region": r2_storage.settings.r2_region,
            "addressing_style": (r2_storage.os.getenv("R2_ADDRESSING_STYLE") or "path"),
            "head_bucket_ok": ok,
            "error": err,
        }

    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"No se pudo diagnosticar R2: {e}")


@router.get("/assets/{asset_id}/open", summary="Abrir asset (redirect a URL pública)")
def open_asset(asset_id: str):
    d = get_asset(asset_id)
    if not d or not d.get("file_url"):
        raise HTTPException(status_code=404, detail="Asset no encontrado")
    # Redirige a la URL pública en R2. Mantiene tu API estable sin exponer claves.
    return RedirectResponse(url=str(d["file_url"]))


@router.get("/assets/{asset_id}/download", summary="Descargar asset (URL firmada)")
def download_asset(asset_id: str):
    d = get_asset(asset_id)
    if not d or not d.get("file_url"):
        raise HTTPException(status_code=404, detail="Asset no encontrado")
    key = r2_storage.derive_key_from_url(str(d["file_url"]))
    if not key:
        raise HTTPException(status_code=400, detail="No se pudo derivar la clave del objeto")
    # Usa el título como nombre sugerido
    name = str(d.get("title") or "documento.pdf")
    url = r2_storage.presign_get_url(key, filename=name)
    return RedirectResponse(url=url)


@router.get("/download", summary="Descargar por URL pública (URL firmada)")
def download_by_url(u: str = Query(..., description="URL pública del objeto en R2")):
    key = r2_storage.derive_key_from_url(u)
    if not key:
        raise HTTPException(status_code=400, detail="URL no válida para R2")
    url = r2_storage.presign_get_url(key)
    return RedirectResponse(url=url)


@router.get("/assets/{asset_id}", response_model=dict, summary="Obtener asset")
def get_asset_by_id(asset_id: str):
    d = get_asset(asset_id)
    if not d:
        raise HTTPException(status_code=404, detail="Asset no encontrado")
    return {"asset": d}


@router.get("/docs/{doc_id}", response_model=dict, summary="Obtener documento (library_doc)")
def get_doc_by_id(doc_id: str):
    d = get_document(doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return {"doc": d}


@router.patch("/assets/{asset_id}/tags", response_model=dict, summary="Actualizar tags de un asset")
def update_asset_tags(asset_id: str, payload: dict = Body(..., description="{ tags: [..] }")):
    try:
        raw = payload.get("tags") if isinstance(payload, dict) else None
        if raw is None:
            raise HTTPException(status_code=422, detail="Body debe incluir 'tags' (lista de strings)")
        if isinstance(raw, str):
            tags_list = [p.strip() for p in raw.split(",") if p.strip()]
        else:
            tags_list = [str(t).strip() for t in (raw or []) if str(t).strip()]
        ok = repo_update_asset_tags(asset_id, tags_list)
        if not ok:
            raise HTTPException(status_code=404, detail="Asset no encontrado o sin cambios")
        return {"message": "ok", "id": asset_id, "tags": tags_list}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron actualizar las tags: {e}")


@router.patch("/docs/{doc_id}/tags", response_model=dict, summary="Actualizar tags de un documento (library_doc)")
def update_doc_tags(doc_id: str, payload: dict = Body(..., description="{ tags: [..] }")):
    try:
        raw = payload.get("tags") if isinstance(payload, dict) else None
        if raw is None:
            raise HTTPException(status_code=422, detail="Body debe incluir 'tags' (lista de strings)")
        if isinstance(raw, str):
            tags_list = [p.strip() for p in raw.split(",") if p.strip()]
        else:
            tags_list = [str(t).strip() for t in (raw or []) if str(t).strip()]
        ok = update_document_tags(doc_id, tags_list)
        if not ok:
            raise HTTPException(status_code=404, detail="Documento no encontrado o sin cambios")
        return {"message": "ok", "id": doc_id, "tags": tags_list}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron actualizar las tags: {e}")

@router.post("/rag/upload", response_model=dict, summary="Subir documento para RAG (R2 → library_doc) en library/rag")
async def upload_rag_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(default=None, description="Lista separada por comas"),
    prefix: Optional[str] = Form(default="library/rag/", description="Prefijo en R2, p.ej. library/rag/calendarios/"),
    source_is_pdf: Optional[bool] = Form(default=False, description="Marcar URL fuente como PDF oficial"),
):
    try:
        return await _upload_r2_by_type(
            file=file,
            type_="rag",
            title=title,
            tags=tags,
            prefix=prefix,
            source_is_pdf=source_is_pdf,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo subir el documento RAG: {e}")
