"""Repositorio para subir archivos a Cloudflare R2 (S3 compatible).

Devuelve la URL pública resultante para referenciarla como attachment o en metadatos.
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

from app.infrastructure.storage.r2 import get_s3_client, public_base_url
from app.core.config import settings


async def upload_uploadfile_to_r2(upload_file, prefix: str = "chat/") -> str:
    """Sube un UploadFile a R2. Retorna la URL pública.

    Nota: ejecuta el put_object en un thread para no bloquear el event loop.
    """
    import asyncio

    bucket = settings.r2_bucket or os.getenv("R2_BUCKET")
    base = public_base_url()
    if not bucket or not base:
        raise RuntimeError("R2 no configurado (R2_BUCKET/R2_PUBLIC_BASE_URL)")

    name = upload_file.filename or "file"
    ext = ""
    if "." in name:
        ext = name[name.rfind("."):]
    key = f"{prefix}{uuid.uuid4().hex}{ext}"
    content_type = upload_file.content_type or "application/octet-stream"

    # Usa el archivo subyacente (SpooledTemporaryFile) como fileobj
    fileobj = upload_file.file
    fileobj.seek(0)

    s3 = get_s3_client()

    def _put():
        s3.put_object(Bucket=bucket, Key=key, Body=fileobj, ContentType=content_type)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _put)

    return base.rstrip("/") + "/" + key
