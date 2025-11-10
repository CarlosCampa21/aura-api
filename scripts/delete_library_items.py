"""Borrador seguro para library_asset / library_doc (+chunks) y objetos en R2.

Uso típico:
  PYTHONPATH=. python scripts/delete_library_items.py \
    --query "laboratorio y salon dsc-39 pa entrada" \
    --query "servidores ad-46 pb entrada" \
    --delete-r2 --yes

Características:
  - Busca en `library_asset` y/o `library_doc` por título/tags (regex robusto).
  - Para `library_doc`, elimina también sus `library_chunk` (RAG) salvo que se use --no-chunks.
  - Si se pasa --delete-r2, borra el objeto en R2 derivando la clave desde la URL pública.
  - Dry‑run por defecto (muestra qué se borraría). Confirma con --yes.
"""
from __future__ import annotations

import argparse
import re
from typing import Iterable, List, Dict, Any

from bson import ObjectId

from app.core.config import settings
from app.infrastructure.db.mongo import get_db, init_mongo
from app.infrastructure.storage.r2 import get_s3_client, derive_key_from_url
from app.repositories.library_chunk_repo import delete_by_doc_id


def _compile_regex(q: str) -> Any:
    q = (q or "").strip()
    # Permite espacios como comodines: "a b" -> ".*a.*b.*"
    pattern = ".*" + re.escape(q).replace("\\ ", ".*?") + ".*"
    return re.compile(pattern, re.IGNORECASE)


def _find_assets(queries: List[str]) -> List[Dict[str, Any]]:
    db = get_db()
    ors = []
    for q in queries:
        r = _compile_regex(q)
        ors.append({"title": r})
        ors.append({"tags": r})
    filtro = {"$or": ors} if ors else {}
    cur = db["library_asset"].find(
        filtro,
        {"title": 1, "tags": 1, "url": 1, "mime_type": 1},
    )
    out: List[Dict[str, Any]] = []
    for d in cur:
        d["id"] = str(d.pop("_id"))
        out.append(d)
    return out


def _find_docs(queries: List[str]) -> List[Dict[str, Any]]:
    db = get_db()
    ors = []
    for q in queries:
        r = _compile_regex(q)
        ors.append({"title": r})
        ors.append({"tags": r})
    filtro = {"$or": ors} if ors else {}
    cur = db["library_doc"].find(
        filtro,
        {"title": 1, "tags": 1, "url": 1, "kind": 1},
    )
    out: List[Dict[str, Any]] = []
    for d in cur:
        d["id"] = str(d.pop("_id"))
        out.append(d)
    return out


def _delete_r2_if_requested(url: str | None, *, actually_delete: bool) -> str:
    if not url:
        return ""
    try:
        key = derive_key_from_url(url)
        if not key:
            return "(sin clave R2)"
        if not actually_delete:
            return key
        s3 = get_s3_client()
        bucket = settings.r2_bucket
        s3.delete_object(Bucket=bucket, Key=key)
        return key
    except Exception as e:  # pragma: no cover
        return f"ERROR R2: {e}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", action="append", default=[], help="Texto para buscar por título/tags (se puede repetir)")
    ap.add_argument("--assets", action="store_true", help="Limitar a library_asset")
    ap.add_argument("--docs", action="store_true", help="Limitar a library_doc (+chunks)")
    ap.add_argument("--no-chunks", action="store_true", help="No borrar library_chunk de los docs")
    ap.add_argument("--delete-r2", action="store_true", help="Borrar también el objeto en R2 si hay URL")
    ap.add_argument(
        "--purge-chunks",
        action="store_true",
        help="Además de borrar por doc_id, purga library_chunk cuyo meta.title coincida con --query (regex)",
    )
    ap.add_argument("--yes", action="store_true", help="Confirmar y ejecutar (por defecto es dry-run)")
    args = ap.parse_args()

    init_mongo()
    db = get_db()

    targets = []
    if args.assets or not (args.assets or args.docs):
        targets.append("assets")
    if args.docs or not (args.assets or args.docs):
        targets.append("docs")

    print("Buscando coincidencias…\n")
    to_delete_assets: List[Dict[str, Any]] = []
    to_delete_docs: List[Dict[str, Any]] = []
    if "assets" in targets:
        to_delete_assets = _find_assets(args.query)
    if "docs" in targets:
        to_delete_docs = _find_docs(args.query)

    if to_delete_assets:
        print(f"Assets a borrar: {len(to_delete_assets)}")
        for a in to_delete_assets:
            print(f"  - {a['id']} | {a.get('title','')} | URL={'sí' if a.get('url') else 'no'}")
    else:
        print("Assets a borrar: 0")

    if to_delete_docs:
        print(f"Docs a borrar: {len(to_delete_docs)}")
        for d in to_delete_docs:
            print(f"  - {d['id']} | {d.get('title','')} | kind={d.get('kind','')} | URL={'sí' if d.get('url') else 'no'}")
    else:
        print("Docs a borrar: 0")

    if not args.yes:
        print("\nDry‑run. Añade --yes para ejecutar. Usa --delete-r2 para purgar objetos.")
        return

    print("\nEjecutando eliminaciones…")
    # Ejecuta borrado de assets
    for a in to_delete_assets:
        if args.delete_r2:
            key = _delete_r2_if_requested(a.get("url"), actually_delete=True)
            if key:
                print(f"  R2 eliminado (asset): {key}")
        res = db["library_asset"].delete_one({"_id": ObjectId(a["id"])})
        print(f"  Asset {a['id']} eliminado (ack={res.acknowledged})")

    # Ejecuta borrado de docs (+chunks por doc_id)
    for d in to_delete_docs:
        if not args.no_chunks:
            try:
                n = delete_by_doc_id(d["id"])
            except Exception:
                n = 0
            print(f"  Chunks eliminados (doc {d['id']}): {n}")
        if args.delete_r2:
            key = _delete_r2_if_requested(d.get("url"), actually_delete=True)
            if key:
                print(f"  R2 eliminado (doc): {key}")
        res = db["library_doc"].delete_one({"_id": ObjectId(d["id"])})
        print(f"  Doc {d['id']} eliminado (ack={res.acknowledged})")

    # Purga adicional de chunks por título (regex) usando las queries
    if args.purge_chunks and args.query:
        from app.repositories.library_chunk_repo import delete_by_title  # import lazy
        total = 0
        for q in args.query:
            try:
                n = delete_by_title(q, regex=True)
            except Exception:
                n = 0
            total += n
            print(f"  Chunks eliminados por título ~ /{q}/i: {n}")
        print(f"  Total chunks eliminados por título: {total}")

    print("\nListo.")


if __name__ == "__main__":
    main()
