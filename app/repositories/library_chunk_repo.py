"""Repositorio para chunks y embeddings de documentos (RAG).

Guarda los fragmentos de texto por documento y su embedding asociado
para consulta con Atlas Vector Search.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List
from datetime import datetime, timezone
from bson import ObjectId

from app.infrastructure.db.mongo import get_db

COLL = "library_chunk"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def delete_by_doc_id(doc_id: str) -> int:
    """Elimina todos los chunks asociados a un documento."""
    db = get_db()
    oid = ObjectId(doc_id)
    res = db[COLL].delete_many({"doc_id": oid})
    return int(res.deleted_count)


def delete_by_title(title: str, *, regex: bool = False) -> int:
    """Elimina chunks cuyo `meta.title` coincide con el título dado.

    - Si `regex` es False (default), usa coincidencia exacta del campo.
    - Si `regex` es True, usa expresión regular insensible a mayúsculas.
    """
    db = get_db()
    if not title:
        return 0
    filtro = {"meta.title": title} if not regex else {"meta.title": {"$regex": title, "$options": "i"}}
    res = db[COLL].delete_many(filtro)
    return int(res.deleted_count)


def bulk_insert_chunks(doc_id: str, chunks: Iterable[Dict[str, Any]]) -> int:
    """Inserta en bloque chunks ya procesados para un documento.

    Cada item debe incluir: chunk_index (int), text (str),
    y opcionalmente: page (int), embedding (list[float]), meta (dict).
    """
    db = get_db()
    now = _now_iso()
    oid = ObjectId(doc_id)
    docs: List[Dict[str, Any]] = []
    for c in chunks:
        d = {
            "doc_id": oid,
            "chunk_index": int(c.get("chunk_index", 0)),
            "text": str(c.get("text", "")),
            "created_at": now,
            "updated_at": now,
        }
        if "page" in c:
            d["page"] = int(c["page"]) if c["page"] is not None else None
        if "embedding" in c:
            d["embedding"] = [float(x) for x in (c["embedding"] or [])]
        if "meta" in c:
            d["meta"] = dict(c["meta"]) if c["meta"] is not None else None
        docs.append(d)

    if not docs:
        return 0
    res = db[COLL].insert_many(docs)
    return len(res.inserted_ids)


def count_by_doc_id(doc_id: str) -> int:
    db = get_db()
    oid = ObjectId(doc_id)
    return int(db[COLL].count_documents({"doc_id": oid}))


def knn_search(vector: list[float], k: int = 5, index_name: str = "rag_embedding") -> list[dict]:
    """Consulta vectorial usando Atlas Vector Search ($search knnBeta).

    Retorna documentos con campos: doc_id (str), chunk_index, text, score.
    """
    db = get_db()
    coll = db[COLL]
    pipeline = [
        {
            "$search": {
                "index": index_name,
                "knnBeta": {
                    "path": "embedding",
                    "vector": vector,
                    "k": int(k),
                },
            }
        },
        {
            "$project": {
                "doc_id": 1,
                "chunk_index": 1,
                "text": 1,
                "meta": 1,
                "score": {"$meta": "searchScore"},
            }
        },
        {"$limit": int(k)},
    ]
    rows = list(coll.aggregate(pipeline))
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "doc_id": str(r.get("doc_id")),
                "chunk_index": int(r.get("chunk_index", 0)),
                "text": r.get("text") or "",
                "meta": r.get("meta") or {},
                "score": float(r.get("score", 0.0)),
            }
        )
    return out
