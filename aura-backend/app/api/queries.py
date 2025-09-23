# app/api/queries.py
from fastapi import APIRouter, HTTPException, status, Query
from pydantic import EmailStr
from typing import Optional
from app.domain.queries.schemas import QueryCreate, QueryOut
from app.repositories.queries_repo import insert_query, list_queries

router = APIRouter(prefix="/queries", tags=["Queries"])

@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_query(payload: QueryCreate):
    try:
        inserted_id = insert_query(payload.model_dump(mode="json"))
        # La respuesta completa la devuelve mejor el GET; aquí regresamos eco.
        out = QueryOut(
            usuario_correo=str(payload.usuario_correo),
            pregunta=payload.pregunta,
            respuesta=payload.respuesta or "",
            ts=payload.ts or "",
        ).model_dump()
        return {"message": "ok", "id": inserted_id, "data": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert consulta failed: {e}")

@router.get("", response_model=dict)
def get_queries(usuario_correo: Optional[EmailStr] = Query(default=None)):
    try:
        items = list_queries(str(usuario_correo) if usuario_correo else None)
        return {"consultas": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query consultas failed: {e}")
