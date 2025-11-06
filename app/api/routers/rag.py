"""API para ingesta RAG (multi-formato) y futuras búsquedas vectoriales.

Por ahora: endpoints para ingestar un documento o varios.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from app.core.config import settings

from app.services.rag_ingest_service import ingest_document
from app.repositories.library_repo import list_active_documents
from app.services.rag_search_service import answer_with_rag


router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/ingest/{doc_id}", summary="Ingestar un documento (PDF/TXT/DOCX/XLSX/CSV/MD)")
def ingest_one(doc_id: str):
    try:
        res = ingest_document(doc_id)
        return {"message": "ok", **res}
    except HTTPException:
        raise
    except ValueError as e:
        # Errores de validación (p.ej., documento no elegible para RAG) → 400
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo ingestar: {e}")


@router.post("/ingest-all", summary="Ingestar todos los documentos activos (lote)")
def ingest_all(limit: int = Query(100, ge=1, le=1000)):
    try:
        docs = list_active_documents(limit=limit)
        results = []
        for d in docs:
            try:
                r = ingest_document(d["id"])  # type: ignore
                results.append({"id": d["id"], **r})
            except Exception as e:  # pragma: no cover
                results.append({"id": d.get("id"), "error": str(e)})
        return {"message": "ok", "count": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo ingestar en lote: {e}")


@router.get("/search", summary="Búsqueda RAG con respuesta redactada (sin fuentes)")
def rag_search(q: str = Query(..., min_length=2), k: int = Query(default=settings.rag_k_default, ge=1, le=10)):
    try:
        res = answer_with_rag(q, k=k)
        return {"message": "ok", **res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo buscar: {e}")
