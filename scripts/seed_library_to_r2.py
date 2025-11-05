"""Seed de documentos institucionales hacia Cloudflare R2 (S3-compatible).

Sube archivos a un bucket R2 y crea metadatos en `library_doc` con `url` pública.

Env vars requeridas:
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_PUBLIC_BASE_URL

Uso:
  PYTHONPATH=. python scripts/seed_library_to_r2.py /ruta/al/dir --prefix=formats/
  (opcional) manifest.json en el directorio con title/aliases/tags por archivo.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from typing import Dict, Any
from datetime import datetime, timezone

from pymongo import MongoClient

from app.core.config import settings
from app.infrastructure.storage.r2 import get_s3_client, public_base_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Directorio con PDFs/imagenes a cargar")
    parser.add_argument("--prefix", default="", help="Prefijo de clave en el bucket (ej. formats/)")
    parser.add_argument("--department", default=None)
    parser.add_argument("--program", default=None)
    parser.add_argument("--campus", default=None)
    args = parser.parse_args()

    base = os.path.abspath(args.path)
    if not os.path.isdir(base):
        raise SystemExit(f"No es un directorio: {base}")

    manifest_path = os.path.join(base, "manifest.json")
    manifest: Dict[str, Any] = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh) or {}

    bucket = settings.r2_bucket or os.getenv("R2_BUCKET")
    base_url = public_base_url()
    if not bucket or not base_url:
        raise SystemExit("Config R2 incompleta (R2_BUCKET/R2_PUBLIC_BASE_URL)")

    s3 = get_s3_client()
    client = MongoClient(settings.mongo_uri)
    db = client[settings.mongo_db]

    def _now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    count = 0
    for name in sorted(os.listdir(base)):
        if name.startswith(".") or name == "manifest.json":
            continue
        path = os.path.join(base, name)
        if not os.path.isfile(path):
            continue

        key = f"{args.prefix}{name}" if args.prefix else name
        content_type, _ = mimetypes.guess_type(name)
        content_type = content_type or "application/octet-stream"
        with open(path, "rb") as fh:
            s3.put_object(Bucket=bucket, Key=key, Body=fh, ContentType=content_type)
        url = base_url.rstrip("/") + "/" + key

        meta = manifest.get(name) or {}
        title = meta.get("title") or os.path.splitext(name)[0].replace("_", " ").strip()
        aliases = meta.get("aliases") or []
        tags = meta.get("tags") or []
        now = _now_iso()
        doc = {
            "title": title,
            "aliases": aliases,
            "tags": [str(t).strip().lower() for t in tags],
            "department": args.department,
            "program": args.program,
            "campus": args.campus,
            "status": "active",
            "url": url,
            "content_type": content_type,
            "size": os.path.getsize(path),
            "created_at": now,
            "updated_at": now,
        }
        db["library_doc"].insert_one(doc)
        count += 1
        print(f"Uploaded: {key} -> {url}")

    print(f"Done. Inserted {count} documents from {base}")


if __name__ == "__main__":
    main()
