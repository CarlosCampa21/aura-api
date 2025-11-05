"""API de documentos institucionales.

Permite:
- Buscar y obtener metadatos (usa URLs públicas en R2)
- Subir un archivo (PDF/imagen) a R2 y registrar sus metadatos
"""
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import RedirectResponse

from app.repositories.library_repo import search_documents, get_document, insert_document
from app.repositories.files_repo_r2 import upload_uploadfile_to_r2
from app.infrastructure.storage import r2 as r2_storage


router = APIRouter(prefix="/library", tags=["Library"])


@router.get("/search", response_model=dict, summary="Buscar documentos")
def search(q: str = Query(..., min_length=2), limit: int = Query(5, ge=1, le=20)):
    try:
        items = search_documents(q, limit=limit)
        return {"results": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo buscar: {e}")


@router.post("/upload", response_model=dict, summary="Subir documento a R2 y registrar metadatos")
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    aliases: Optional[str] = Form(default=None, description="Lista separada por comas"),
    tags: Optional[str] = Form(default=None, description="Lista separada por comas"),
    department: Optional[str] = Form(default=None),
    program: Optional[str] = Form(default=None),
    campus: Optional[str] = Form(default=None),
    prefix: Optional[str] = Form(default="library/", description="Prefijo en R2, p.ej. library/docentes/"),
):
    try:
        # Validación simple de tipo
        ctype = (file.content_type or "").lower()
        allowed = {
            # Documentos
            "application/pdf",
            "text/plain",
            "text/markdown",
            "text/csv",
            "application/csv",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",       # xlsx
            # Imágenes comunes (por si se requieren en otros flujos)
            "image/jpeg",
            "image/png",
            "image/webp",
        }
        if ctype not in allowed:
            raise HTTPException(status_code=415, detail=f"Tipo no permitido: {ctype}")

        # Sube a R2
        pf = (prefix or "library/").strip()
        if not pf.endswith("/"):
            pf = pf + "/"
        url = await upload_uploadfile_to_r2(file, prefix=pf)

        # Parseo de listas
        def _split_csv(s: Optional[str]) -> List[str]:
            if not s:
                return []
            return [p.strip() for p in s.split(",") if p.strip()]

        doc = {
            "title": title or (file.filename or "Documento"),
            "aliases": _split_csv(aliases),
            "tags": _split_csv(tags),
            "department": department,
            "program": program,
            "campus": campus,
            "status": "active",
            "url": url,
            "content_type": ctype,
        }

        # Inserta metadatos en library_doc (sync)
        doc_id = insert_document(doc)
        return {"message": "ok", "id": doc_id, "title": doc["title"], "url": url}
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


@router.get("/{doc_id}/open", summary="Abrir documento (redirect a URL pública)")
def open_document(doc_id: str):
    d = get_document(doc_id)
    if not d or not d.get("file_url"):
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    # Redirige a la URL pública en R2. Mantiene tu API estable sin exponer claves.
    return RedirectResponse(url=str(d["file_url"]))


@router.get("/{doc_id}/download", summary="Descargar documento (URL firmada)")
def download_document(doc_id: str):
    d = get_document(doc_id)
    if not d or not d.get("file_url"):
        raise HTTPException(status_code=404, detail="Documento no encontrado")
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


@router.get("/{doc_id}", response_model=dict, summary="Obtener documento")
def get(doc_id: str):
    d = get_document(doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return {"document": d}
