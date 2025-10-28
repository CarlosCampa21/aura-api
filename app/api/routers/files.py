"""Endpoints asíncronos para subir/descargar archivos (imágenes/PDF) con GridFS.

Pensado para uso de Aura (adjuntos/descargas) sin migrar todo a async.
"""
from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from app.repositories.files_repo_async import upload_bytes_iter, open_download_stream


router = APIRouter(prefix="/files", tags=["Files"])


@router.post("", response_model=dict, summary="Subir archivo (GridFS)")
async def upload(file: UploadFile = File(...)):
    try:
        async def _chunks():
            # Lee en trozos sin cargar todo en memoria
            size = 256 * 1024
            while True:
                data = await file.read(size)
                if not data:
                    break
                yield data

        file_id = await upload_bytes_iter(
            filename=file.filename or "file",
            content_type=(file.content_type or "application/octet-stream"),
            data_iter=_chunks(),
            metadata={},
        )
        return {
            "message": "ok",
            "id": file_id,
            "filename": file.filename,
            "content_type": file.content_type,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo subir el archivo: {e}")


@router.get("/{file_id}", summary="Descargar/visualizar archivo")
async def download(file_id: str):
    try:
        name, content_type, length, aiter = await open_download_stream(file_id)
        headers = {}
        # Intenta inline para imágenes/PDF
        if content_type.startswith("image/") or content_type == "application/pdf":
            headers["Content-Disposition"] = f'inline; filename="{name}"'
        else:
            headers["Content-Disposition"] = f'attachment; filename="{name}"'
        if length:
            headers["Content-Length"] = str(length)
        return StreamingResponse(aiter, media_type=content_type, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {e}")

