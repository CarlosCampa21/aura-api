from __future__ import annotations

"""CLI: Ingestar documentos a RAG usando los servicios del backend.

Uso:
  python -m rag.ingest --doc-id <id>
  python -m rag.ingest --all --limit 100
"""

import argparse
import json
from typing import Any

from app.services.rag_ingest_service import ingest_document
from app.repositories.library_repo import list_active_documents
from app.infrastructure.db.mongo import init_mongo


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main() -> None:
    # Inicializa conexión Mongo para usar repos/servicios fuera del servidor
    init_mongo()
    p = argparse.ArgumentParser(description="Ingesta RAG (documento o lote)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--doc-id", help="ID de documento en library_doc")
    g.add_argument("--all", action="store_true", help="Ingestar todos los documentos activos")
    p.add_argument("--limit", type=int, default=100, help="Límite para --all (1..1000)")
    args = p.parse_args()

    if args.doc_id:
        res = ingest_document(args.doc_id)
        _print({"message": "ok", "result": res})
        return

    docs = list_active_documents(limit=max(1, min(args.limit, 1000)))
    results = []
    for d in docs:
        try:
            r = ingest_document(d["id"])  # type: ignore
            results.append({"id": d["id"], **r})
        except Exception as e:  # pragma: no cover
            results.append({"id": d.get("id"), "error": str(e)})
    _print({"message": "ok", "count": len(results), "results": results})


if __name__ == "__main__":
    main()
