#!/usr/bin/env python3
"""
Mueve objetos en R2 (cambia el prefijo/"carpeta") y actualiza `library_doc.url`
en Mongo conservando el mismo `doc_id`. No toca `library_chunk`.

Uso típico (docentes → bajo library/rag/docentes/):
  PYTHONPATH=. python3 scripts/move_r2_and_update_library_doc.py \
    --old-prefix rag/docentes/ \
    --new-prefix library/rag/docentes/ \
    --apply --delete-old

Por defecto hace dry‑run (muestra lo que haría). Pasa --apply para ejecutar.
"""
from __future__ import annotations

import argparse
from typing import List
import re

from bson import ObjectId

from app.infrastructure.db.mongo import init_mongo, get_db
from app.infrastructure.storage.r2 import get_s3_client, derive_key_from_url, public_base_url
from app.core.config import settings


def _eligible_docs(old_prefix: str, kind: str | None, tag: str | None) -> List[dict]:
    db = get_db()
    # Construye una regex segura que busque el prefijo en la URL pública
    pattern = "/" + re.escape(old_prefix)
    filtro: dict = {"url": {"$regex": pattern}}
    if kind:
        filtro["kind"] = kind
    if tag:
        filtro["tags"] = tag
    projection = {"title": 1, "url": 1, "tags": 1, "kind": 1}
    return list(db["library_doc"].find(filtro, projection))


def main() -> None:
    ap = argparse.ArgumentParser(description="Mover objetos R2 y actualizar library_doc.url (dry-run por defecto)")
    ap.add_argument("--old-prefix", required=True, help="Prefijo actual en R2 (ej. rag/docentes/)")
    ap.add_argument("--new-prefix", required=True, help="Prefijo destino en R2 (ej. library/rag/docentes/)")
    ap.add_argument("--kind", default=None, help="Filtrar por library_doc.kind (opcional)")
    ap.add_argument("--tag", default=None, help="Filtrar por tag (opcional)")
    ap.add_argument("--apply", action="store_true", help="Ejecutar cambios (por defecto solo muestra)")
    ap.add_argument("--delete-old", action="store_true", help="Eliminar objeto origen tras copiar")
    args = ap.parse_args()

    init_mongo()
    base = (public_base_url() or "").rstrip("/")
    if not base:
        raise SystemExit("R2_PUBLIC_BASE_URL/R2_BUCKET no configurado")

    db = get_db()
    s3 = get_s3_client()
    bucket = settings.r2_bucket
    if not bucket:
        raise SystemExit("R2_BUCKET no configurado en settings/env")

    docs = _eligible_docs(args.old_prefix, args.kind, args.tag)
    if not docs:
        print("No hay documentos que coincidan con el prefijo dado.")
        return

    print(f"Encontrados {len(docs)} documentos para mover: {args.old_prefix} -> {args.new_prefix}")
    moved = 0
    for d in docs:
        _id = d.get("_id")
        url = str(d.get("url") or "")
        key = derive_key_from_url(url) or ""
        if not key or not key.startswith(args.old_prefix):
            print(f"- SKIP {str(_id)}: key no coincide con prefijo ({key})")
            continue
        new_key = args.new_prefix + key[len(args.old_prefix):]
        new_url = f"{base}/{new_key}"
        title = d.get("title") or ""
        if not args.apply:
            print(f"- DRY {str(_id)}: {key} -> {new_key} | URL: {url} -> {new_url} | {title}")
            moved += 1
            continue

        # Copia en R2
        s3.copy_object(Bucket=bucket, CopySource=f"{bucket}/{key}", Key=new_key)
        if args.delete_old:
            s3.delete_object(Bucket=bucket, Key=key)
        # Actualiza URL en library_doc
        db["library_doc"].update_one({"_id": ObjectId(_id)}, {"$set": {"url": new_url}})
        print(f"- OK  {str(_id)}: {key} -> {new_key}")
        moved += 1

    print(f"Listo. {'Movidos' if args.apply else 'Aptos'}: {moved}")


if __name__ == "__main__":
    main()
