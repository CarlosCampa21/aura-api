from __future__ import annotations

"""CLI: Responder con RAG usando el servicio de búsqueda/redacción."""

import argparse
import json
from typing import Any

from app.services.rag_search_service import answer_with_rag


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description="Respuesta RAG (redacción breve)")
    p.add_argument("--q", required=True, help="Pregunta/consulta")
    p.add_argument("--k", type=int, default=5, help="Vecinos a usar")
    args = p.parse_args()

    res = answer_with_rag(args.q, k=max(1, args.k))
    _print({"message": "ok", **res})


if __name__ == "__main__":
    main()

