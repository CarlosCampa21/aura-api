from __future__ import annotations

"""CLI: Recuperación KNN (sin redacción) para inspeccionar evidencia."""

import argparse
import json
from typing import Any

from app.infrastructure.ai.embeddings import embed_texts
from app.repositories.library_chunk_repo import knn_search


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description="Retrieve KNN de chunks (RAG)")
    p.add_argument("--q", required=True, help="Pregunta/consulta")
    p.add_argument("--k", type=int, default=5, help="Vecinos a recuperar")
    args = p.parse_args()

    vec = embed_texts([args.q])[0]
    hits = knn_search(vec, k=max(1, args.k))
    _print({"message": "ok", "q": args.q, "k": args.k, "hits": hits})


if __name__ == "__main__":
    main()

