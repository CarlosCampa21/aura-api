"""API de consulta de documentos institucionales (sólo lectura).

Permite buscar por texto y obtener metadatos; el binario se sirve vía /files/{file_id}
o mediante URL externa almacenada en el documento.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.repositories.library_repo import search_documents, get_document


router = APIRouter(prefix="/library", tags=["Library"])


@router.get("/search", response_model=dict, summary="Buscar documentos")
def search(q: str = Query(..., min_length=2), limit: int = Query(5, ge=1, le=20)):
    try:
        items = search_documents(q, limit=limit)
        return {"results": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo buscar: {e}")


@router.get("/{doc_id}", response_model=dict, summary="Obtener documento")
def get(doc_id: str):
    d = get_document(doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return {"document": d}

