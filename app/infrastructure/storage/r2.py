"""Cliente S3-compatible para Cloudflare R2.

Se usa para subir archivos públicos y guardar su URL en `library_doc.url`.
"""
from __future__ import annotations

import os
from typing import Optional

import boto3
from app.core.config import settings
from botocore.config import Config


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
