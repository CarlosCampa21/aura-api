"""Repositorio de assets descargables (PDFs/imagenes) almacenados en R2.

Colección: library_asset
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from bson import ObjectId

from app.infrastructure.db.mongo import get_db

COLL = "library_asset"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_asset(doc: Dict[str, Any]) -> str:
    db = get_db()
    data = dict(doc)
    now = _now_iso()
    data.setdefault("enabled", True)
    data.setdefault("downloadable", True)
    data.setdefault("version", 1)
    data.setdefault("kind", "asset")
    data.setdefault("created_at", now)
    data["updated_at"] = now

    if isinstance(data.get("tags"), list):
        data["tags"] = [str(t).strip().lower() for t in data["tags"] if t]
    else:
        data["tags"] = []

    res = db[COLL].insert_one(data)
    return str(res.inserted_id)


def get_asset(asset_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    try:
        oid = ObjectId(asset_id)
    except Exception:
        return None
    d = db[COLL].find_one({"_id": oid})
    if not d:
        return None
    d["id"] = str(d.pop("_id"))
    if d.get("url"):
        d["file_url"] = str(d["url"])  # homogéneo con library_repo
    return d


def search_assets(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Búsqueda simple por title/tags para listar assets activos."""
    db = get_db()
    import re
    q = (query or "").strip()
    if not q:
        return []
    regex = re.compile(".*" + re.escape(q).replace("\\ ", ".*?") + ".*", re.IGNORECASE)
    filtro = {
        "enabled": True,
        "$or": [
            {"title": regex},
            {"tags": regex},
        ],
    }
    projection = {
        "title": 1,
        "mime_type": 1,
        "url": 1,
        "tags": 1,
        "version": 1,
        "doc_ref": 1,
    }
    rows = list(db[COLL].find(filtro, projection).limit(int(limit)))
    out: List[Dict[str, Any]] = []
    for r in rows:
        item: Dict[str, Any] = {
            "id": str(r.get("_id")),
            "title": r.get("title") or "",
            "mime_type": r.get("mime_type") or "application/octet-stream",
            "tags": r.get("tags") or [],
            "version": r.get("version") or 1,
        }
        if r.get("url"):
            item["file_url"] = str(r["url"])  # URL pública R2
        if r.get("doc_ref"):
            item["doc_ref"] = str(r["doc_ref"])  # referencia a library_doc
        out.append(item)
    return out

