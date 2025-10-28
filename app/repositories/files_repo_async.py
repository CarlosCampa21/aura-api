"""Repositorio asíncrono de archivos usando GridFS (Motor).

Provee utilidades para subir y descargar archivos en streaming sin bloquear.
"""
from __future__ import annotations

from typing import AsyncIterator, Dict, Any, Tuple
from bson import ObjectId

from app.infrastructure.db.mongo_async import get_gridfs_bucket


async def upload_bytes_iter(
    filename: str,
    content_type: str | None,
    data_iter: AsyncIterator[bytes],
    metadata: Dict[str, Any] | None = None,
) -> str:
    """Sube un archivo a GridFS desde un iterador asíncrono de bytes.

    Devuelve el id como string.
    """
    bucket = get_gridfs_bucket()
    gridin = await bucket.open_upload_stream(
        filename,
        metadata={"content_type": content_type or "application/octet-stream", **(metadata or {})},
    )
    try:
        async for chunk in data_iter:
            if chunk:
                await gridin.write(chunk)
    finally:
        await gridin.close()
    # _id es un ObjectId
    return str(gridin._id)


async def open_download_stream(file_id: str) -> Tuple[str, str, int, AsyncIterator[bytes]]:
    """Abre un stream de lectura desde GridFS y retorna metadatos y un iterador async.

    Retorna (filename, content_type, length, async_iter_bytes)
    """
    bucket = get_gridfs_bucket()
    oid = ObjectId(file_id)
    gridout = await bucket.open_download_stream(oid)
    filename = gridout.filename or file_id
    length = getattr(gridout, "length", 0) or 0
    meta = getattr(gridout, "metadata", {}) or {}
    content_type = meta.get("content_type") or "application/octet-stream"

    async def _aiter() -> AsyncIterator[bytes]:
        try:
            chunk_size = 256 * 1024
            while True:
                data = await gridout.read(chunk_size)
                if not data:
                    break
                yield data
        finally:
            await gridout.close()

    return filename, content_type, int(length), _aiter()

