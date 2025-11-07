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
from app.infrastructure.db.mongo import init_mongo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Directorio con archivos a cargar (pdf/txt/docx/xlsx/csv/md)")
    parser.add_argument("--prefix", default="", help="Prefijo de clave en el bucket (ej. rag/docentes/)")
    parser.add_argument("--department", default=None)
    parser.add_argument("--program", default=None)
    parser.add_argument("--campus", default=None)
    parser.add_argument("--kind", default=None, help="Valor para library_doc.kind (ej. rag)")
    parser.add_argument("--enabled", type=lambda v: str(v).lower() not in {"0","false","no"}, default=True, help="library_doc.enabled (default: true)")
    parser.add_argument("--tags", default="", help="Lista de tags separados por coma (se agregan a los del manifest)")
    parser.add_argument("--title-first-line", action="store_true", help="Usar primera línea del archivo de texto como título (txt/md/csv)")
    parser.add_argument("--ingest", action="store_true", help="Tras subir e insertar en library_doc, ingesta cada documento para generar chunks/embeddings")
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
    # Inicializa el cliente global usado por los servicios (para ingesta)
    init_mongo()
    client = MongoClient(settings.mongo_uri)
    db = client[settings.mongo_db]
    # Import tardío para no requerir dependencias de AI si no se usa --ingest
    if args.ingest:
        try:
            from app.services.rag_ingest_service import ingest_document  # type: ignore
        except Exception as e:
            raise SystemExit(f"No se pudo importar rag_ingest_service: {e}")

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
        # Título: manifest > primera línea (si aplica y flag activo) > nombre de archivo
        title = meta.get("title")
        if not title and args.title_first_line and (content_type.startswith("text/") or name.lower().endswith(('.md','.txt','.csv'))):
            try:
                with open(path, "r", encoding="utf-8") as tf:
                    for line in tf:
                        t = line.strip().lstrip("\ufeff")
                        if t:
                            title = t[:140]
                            break
            except Exception:
                title = None
        if not title:
            title = os.path.splitext(name)[0].replace("_", " ").strip()
        aliases = meta.get("aliases") or []
        # Combina tags del manifest con los de --tags
        tags = (meta.get("tags") or []) + ([t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else [])
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        doc = {
            "title": title,
            "aliases": aliases,
            "tags": [str(t).strip().lower() for t in tags],
            "department": args.department,
            "program": args.program,
            "campus": args.campus,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "url": url,
            "content_type": content_type,
            "size": os.path.getsize(path),
        }
        if args.kind:
            doc["kind"] = args.kind
        doc["enabled"] = bool(args.enabled)
        res = db["library_doc"].insert_one(doc)
        inserted_id = str(res.inserted_id)
        count += 1
        print(f"Uploaded: {key} -> {url} (doc_id={inserted_id})")
        if args.ingest and args.kind and args.kind.lower() == "rag":
            try:
                r = ingest_document(inserted_id)  # type: ignore
                print(f"  Ingested {inserted_id}: {r}")
            except Exception as e:  # pragma: no cover
                print(f"  Ingest error for {inserted_id}: {e}")

    print(f"Done. Inserted {count} documents from {base}")


if __name__ == "__main__":
    main()
