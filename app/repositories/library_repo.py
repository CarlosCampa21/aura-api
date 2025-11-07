"""Repositorio de documentos institucionales (biblioteca).

Guarda metadatos y punteros a archivos (GridFS via file_id o URL externa).
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from bson import ObjectId

from app.infrastructure.db.mongo import get_db

COLL = "library_doc"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_document(doc: Dict[str, Any]) -> str:
    db = get_db()
    data = dict(doc)
    now = _now_iso()
    data.setdefault("status", "active")
    data.setdefault("created_at", now)
    data["updated_at"] = now
    # Normaliza campos
    if isinstance(data.get("aliases"), list):
        data["aliases"] = [str(a).strip() for a in data["aliases"] if a]
    else:
        data["aliases"] = []
    if isinstance(data.get("tags"), list):
        data["tags"] = [str(t).strip().lower() for t in data["tags"] if t]
    else:
        data["tags"] = []
    res = db[COLL].insert_one(data)
    return str(res.inserted_id)


def _norm(s: str) -> str:
    import unicodedata, re
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def search_documents(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    db = get_db()
    q = (_norm(query) if query else "").strip()
    if not q:
        return []
    # Estrategia simple: regex OR en title, aliases, tags
    import re
    regex = re.compile(".*" + re.escape(q).replace("\\ ", ".*?") + ".*", re.IGNORECASE)
    # Para arrays de strings (aliases/tags) se puede hacer match directo con regex
    filtro = {
        "status": "active",
        "$or": [
            {"title": regex},
            {"aliases": regex},
            {"tags": regex},
        ],
    }
    projection = {
        "title": 1,
        "aliases": 1,
        "tags": 1,
        "content_type": 1,
        "size": 1,
        "url": 1,
    }
    docs = list(db[COLL].find(filtro, projection).limit(int(limit)))
    # Post-procesa ids y URLs
    out: List[Dict[str, Any]] = []
    for d in docs:
        d_out: Dict[str, Any] = {
            "id": str(d.get("_id")),
            "title": d.get("title") or "",
            "aliases": d.get("aliases") or [],
            "tags": d.get("tags") or [],
            "content_type": d.get("content_type") or "application/octet-stream",
        }
        if d.get("url"):
            d_out["file_url"] = str(d["url"])  # externo (R2/CDN)
        out.append(d_out)
    return out


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    try:
        oid = ObjectId(doc_id)
    except Exception:
        return None
    d = db[COLL].find_one({"_id": oid})
    if not d:
        return None
    d["id"] = str(d.pop("_id"))
    if d.get("url"):
        d["file_url"] = str(d["url"])
    return d


def list_active_documents(limit: int = 100, skip: int = 0) -> list[Dict[str, Any]]:
    """Lista documentos activos elegibles para ingesta RAG.

    Solo devuelve documentos de library_doc con kind == "rag" y (enabled == True o sin campo),
    con URL presente.
    """
    db = get_db()
    projection = {
        "title": 1,
        "url": 1,
        "content_type": 1,
        "status": 1,
        "kind": 1,
        "enabled": 1,
    }
    filtro = {
        "status": "active",
        "url": {"$ne": None},
        "kind": "rag",
        "$or": [
            {"enabled": True},
            {"enabled": {"$exists": False}},
        ],
    }
    cur = db[COLL].find(filtro, projection).skip(int(skip)).limit(int(limit))
    out: list[Dict[str, Any]] = []
    for d in cur:
        out.append({
            "id": str(d.get("_id")),
            "title": d.get("title") or "",
            "url": d.get("url"),
            "content_type": d.get("content_type"),
        })
    return out
