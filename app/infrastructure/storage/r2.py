"""Cliente S3-compatible para Cloudflare R2.

Se usa para subir archivos públicos y guardar su URL en `library_doc.url`.
"""
from __future__ import annotations

import os
from typing import Optional

import boto3
from app.core.config import settings
from botocore.config import Config
from urllib.parse import urlparse, unquote


def _endpoint_url() -> str:
    # S3 API endpoint (p. ej. https://<account>.r2.cloudflarestorage.com)
    ep = settings.r2_endpoint or os.getenv("R2_ENDPOINT")
    if ep:
        return ep
    # Fallback a formato con account id si se proporciona
    account_id = os.getenv("R2_ACCOUNT_ID", "")
    return f"https://{account_id}.r2.cloudflarestorage.com"


def get_s3_client():
    style = (os.getenv("R2_ADDRESSING_STYLE") or "path").lower()
    if style not in ("path", "virtual"):
        style = "path"
    cfg = Config(signature_version="s3v4", s3={"addressing_style": style})
    return boto3.client(
        "s3",
        aws_access_key_id=settings.r2_access_key or os.getenv("R2_ACCESS_KEY") or os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=settings.r2_secret_key or os.getenv("R2_SECRET_KEY") or os.getenv("R2_SECRET_ACCESS_KEY"),
        endpoint_url=_endpoint_url(),
        region_name=(settings.r2_region or os.getenv("R2_REGION") or "auto"),
        config=cfg,
    )


def public_base_url() -> Optional[str]:
    # Preferido: dominio público (R2.dev o personalizado)
    base = settings.r2_public_base_url or os.getenv("R2_PUBLIC_BASE_URL")
    if base:
        return base
    # Fallback: usar el endpoint S3 + bucket como base pública
    bucket = settings.r2_bucket or os.getenv("R2_BUCKET")
    ep = _endpoint_url().rstrip("/")
    if bucket and ep:
        return f"{ep}/{bucket}"
    return None


def derive_key_from_url(url: str) -> Optional[str]:
    """Intenta derivar la clave (key) del objeto a partir de una URL pública.

    Soporta bases con o sin nombre de bucket en la ruta.
    """
    if not url:
        return None
    base = (public_base_url() or "").rstrip("/")
    if base and url.startswith(base + "/"):
        return unquote(url[len(base) + 1 :])
    # Fallback: parsea el path y, si contiene el bucket, lo recorta
    p = urlparse(url)
    path = unquote(p.path or "/").lstrip("/")
    bucket = settings.r2_bucket or os.getenv("R2_BUCKET") or ""
    if path.startswith(bucket + "/"):
        return path[len(bucket) + 1 :]
    return path or None


def presign_get_url(key: str, *, expires: int = 600, filename: Optional[str] = None) -> str:
    """Genera una URL firmada de lectura con Content-Disposition=attachment.

    Requiere R2_BUCKET configurado.
    """
    bucket = settings.r2_bucket or os.getenv("R2_BUCKET")
    if not bucket:
        raise RuntimeError("R2_BUCKET no configurado")
    s3 = get_s3_client()
    params = {"Bucket": bucket, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    else:
        params["ResponseContentDisposition"] = "attachment"
    return s3.generate_presigned_url(
        ClientMethod="get_object", Params=params, ExpiresIn=int(expires)
    )
