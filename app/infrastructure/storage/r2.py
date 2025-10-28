"""Cliente S3-compatible para Cloudflare R2.

Se usa para subir archivos públicos y guardar su URL en `library_doc.url`.
"""
from __future__ import annotations

import os
from typing import Optional

import boto3


def _endpoint_url() -> str:
    account_id = os.getenv("R2_ACCOUNT_ID", "")
    # R2 endpoint: https://<account_id>.r2.cloudflarestorage.com
    return f"https://{account_id}.r2.cloudflarestorage.com"


def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        endpoint_url=_endpoint_url(),
        region_name="auto",
    )


def public_base_url() -> Optional[str]:
    # Ej: https://pub-xxxxxx.r2.dev o tu dominio CDN personalizado
    return os.getenv("R2_PUBLIC_BASE_URL")

