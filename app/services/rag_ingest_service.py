"""Servicio de ingesta RAG: descarga, extrae, chunking, embeddings y persistencia.

Soporta formatos: txt, md, csv, pdf, docx, xlsx. (Sin imágenes/OCR.)
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
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


def _strip_front_matter(text: str) -> str:
    """Elimina front-matter YAML al inicio de archivos Markdown.

    Busca un bloque que comience con '---' al inicio del documento y termine
    con una línea '---' de cierre. Si existe, retorna el contenido después del cierre.
    """
    if not text:
        return text
    if text.startswith("---"):
        # Encuentra el final del bloque --- ... --- en líneas
        m = re.search(r"^---\s*\n.*?\n---\s*\n", text, flags=re.DOTALL)
        if m:
            return text[m.end() :]
    return text


def _is_heading(paragraph: str) -> Optional[str]:
    """Detecta títulos Markdown y devuelve su texto limpio si aplica."""
    if not paragraph:
        return None
    # Estilo #, ##, ###
    m = re.match(r"^\s{0,3}#{1,6}\s+(.+)$", paragraph.strip())
    if m:
        return m.group(1).strip()
    # Underline style (=== o ---) en la siguiente línea. Simplificado: línea única con === o ---
    lines = paragraph.splitlines()
    if len(lines) >= 2:
        if re.match(r"^\s*([-=])\1{2,}\s*$", lines[1]):
            return lines[0].strip()
    return None


def _split_into_chunks_with_sections(
    text: str, *, max_chars: int = 1000, overlap: int = 200
) -> List[Tuple[str, Optional[str]]]:
    """Split por párrafos y retorna lista de (texto, sección_actual)."""
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p and p.strip()]
    chunks: List[Tuple[str, Optional[str]]] = []
    buf: List[str] = []
    cur = 0
    current_section: Optional[str] = None
    for p in paras:
        # Actualiza sección si este párrafo es un heading
        h = _is_heading(p)
        if h:
            current_section = h
        # Arma los bloques por tamaño
        if cur + len(p) + 1 > max_chars and buf:
            text_chunk = "\n\n".join(buf)
            chunks.append((_normalize_whitespace(text_chunk), current_section))
            # overlap de caracteres para continuidad
            tail = text_chunk[-overlap:]
            buf = [tail, p]
            cur = len(tail) + len(p)
        else:
            buf.append(p)
            cur += len(p) + 1
    if buf:
        text_chunk = "\n\n".join(buf)
        chunks.append((_normalize_whitespace(text_chunk), current_section))
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
    # Remueve front-matter YAML si es Markdown u otro texto con '---' inicial
    if (content_type or "").lower().startswith("text/markdown") or (url or "").lower().endswith(".md"):
        text = _strip_front_matter(text)
    if not text or len(text.strip()) == 0:
        # Nada que indexar
        delete_by_doc_id(doc_id)
        return {"chunks": 0, "embeddings": 0, "status": "empty"}

    chunks_with_sections = _split_into_chunks_with_sections(text)
    if not chunks_with_sections:
        delete_by_doc_id(doc_id)
        return {"chunks": 0, "embeddings": 0, "status": "empty"}

    # Heurística: si un chunk contiene solo (o principalmente) un correo, adjúntalo al chunk previo
    merged: List[Tuple[str, Optional[str]]] = []
    email_re = re.compile(r"[\w.\-+]+@\w+[^\s]*", re.IGNORECASE)
    for c, sec in chunks_with_sections:
        if merged and email_re.search(c) and not email_re.search(merged[-1][0]):
            prev_text, prev_sec = merged[-1]
            merged[-1] = (prev_text.rstrip() + "\n" + c.strip(), prev_sec or sec)
        else:
            merged.append((c, sec))
    chunks_with_sections = merged

    # Embeddings por lotes (respetar límites de tokens y tamaño)
    chunk_texts = [c for (c, _sec) in chunks_with_sections]
    vectors = embed_texts(chunk_texts)
    items = []
    title = str(d.get("title") or "").strip()
    for i, ((c, sec), v) in enumerate(zip(chunks_with_sections, vectors)):
        chunk_ref = f"[{title} | {sec}]" if title and sec else (f"[{title}]" if title else None)
        items.append({
            "chunk_index": i,
            "text": c,
            "embedding": v,
            "meta": {
                "title": title,
                "section": sec,
                "chunk_ref": chunk_ref,
            },
        })

    delete_by_doc_id(doc_id)
    n = bulk_insert_chunks(doc_id, items)
    return {"chunks": n, "embeddings": n, "status": "ok"}
