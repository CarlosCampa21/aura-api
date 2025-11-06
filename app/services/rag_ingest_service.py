"""Servicio de ingesta RAG: descarga, extrae, chunking, embeddings y persistencia.

Soporta formatos: txt, md, csv, pdf, docx, xlsx. (Sin imágenes/OCR.)
"""
from __future__ import annotations

from typing import Dict, List, Optional
from io import BytesIO
import re
import requests

from app.repositories.library_repo import get_document
from app.repositories.library_chunk_repo import delete_by_doc_id, bulk_insert_chunks
from app.infrastructure.text import extractors
from app.infrastructure.ai.embeddings import embed_texts
from app.core.config import settings


def _http_get(url: str) -> bytes:
    """Descarga binaria simple con requests."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _split_into_chunks(text: str, *, max_chars: int = 1000, overlap: int = 200) -> List[str]:
    """Split por párrafos con longitud objetivo. Simple y robusto."""
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p and p.strip()]
    chunks: List[str] = []
    buf: List[str] = []
    cur = 0
    for p in paras:
        if cur + len(p) + 1 > max_chars and buf:
            chunks.append("\n\n".join(buf))
            # overlap: toma cola del anterior
            tail = chunks[-1][-overlap:]
            buf = [tail, p]
            cur = len(tail) + len(p)
        else:
            buf.append(p)
            cur += len(p) + 1
    if buf:
        chunks.append("\n\n".join(buf))
    # Normaliza espacios
    chunks = [_normalize_whitespace(c) for c in chunks if c and c.strip()]
    return chunks


def _extract_text_by_mime(data: bytes, content_type: Optional[str], url: Optional[str]) -> str:
    ct = (content_type or "").lower()
    ext = (url or "").lower()
    if any(ct.startswith(x) for x in ("text/plain",)) or ext.endswith(".txt"):
        return extractors.extract_text_from_txt(data)
    if any(ct.startswith(x) for x in ("text/markdown",)) or ext.endswith(".md"):
        return extractors.extract_text_from_md(data)
    if any(ct.startswith(x) for x in ("text/csv", "application/csv")) or ext.endswith(".csv"):
        return extractors.extract_text_from_csv(data)
    if ct.startswith("application/pdf") or ext.endswith(".pdf"):
        text, _ = extractors.extract_text_from_pdf(data)
        return text
    if ct in ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",) or ext.endswith(".docx"):
        return extractors.extract_text_from_docx(data)
    if ct in ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel") or ext.endswith(".xlsx"):
        return extractors.extract_text_from_xlsx(data)
    # Fallback: intentar como texto
    return extractors.extract_text_from_txt(data)


def ingest_document(doc_id: str) -> Dict[str, int | str]:
    """Ingesta un documento desde library_doc.

    Flujo: descarga → extrae texto → chunking → embeddings → inserta en library_chunk.
    """
    d = get_document(doc_id)
    if not d or not d.get("file_url"):
        raise ValueError("Documento no encontrado o sin URL")
    # Acepta sólo documentos de library_doc con kind=rag y habilitados
    if str(d.get("kind") or "").lower() != "rag":
        raise ValueError("Ingesta permitida sólo para library_doc.kind='rag'")
    if d.get("enabled") is False:
        raise ValueError("Documento RAG deshabilitado (enabled=false)")

    url = str(d["file_url"])
    content_type = str(d.get("content_type") or "")

    data = _http_get(url)
    text = _extract_text_by_mime(data, content_type, url)
    if not text or len(text.strip()) == 0:
        # Nada que indexar
        delete_by_doc_id(doc_id)
        return {"chunks": 0, "embeddings": 0, "status": "empty"}

    chunks = _split_into_chunks(text)
    if not chunks:
        delete_by_doc_id(doc_id)
        return {"chunks": 0, "embeddings": 0, "status": "empty"}

    # Embeddings por lotes (respetar límites de tokens y tamaño)
    vectors = embed_texts(chunks)
    items = []
    for i, (c, v) in enumerate(zip(chunks, vectors)):
        items.append({
            "chunk_index": i,
            "text": c,
            "embedding": v,
            "meta": {"title": d.get("title")},
        })

    delete_by_doc_id(doc_id)
    n = bulk_insert_chunks(doc_id, items)
    return {"chunks": n, "embeddings": n, "status": "ok"}
