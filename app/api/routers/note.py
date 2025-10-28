"""
Endpoints para `note` (singular, convención en inglés).
"""
from fastapi import APIRouter, HTTPException, status, Query
from typing import Optional
from app.api.schemas.note import NoteCreate, NoteOut
from app.services.note_service import insert_note, list_notes


router = APIRouter(prefix="/note", tags=["Note"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
    summary="Crear nota",
    description="Crea una nota del usuario con tags y relación opcional a conversación.",
)
def create_note(payload: NoteCreate):
    try:
        inserted_id = insert_note(payload.model_dump(mode="json"))
        out = NoteOut(
            user_id=payload.user_id,
            title=payload.title,
            body=payload.body,
            tags=payload.tags,
            status="active",
            source=payload.source or "manual",
            related_conversation_id=payload.related_conversation_id,
            created_at="",
            updated_at="",
        ).model_dump()
        return {"message": "ok", "id": inserted_id, "data": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo crear la nota: {e}")


@router.get(
    "",
    response_model=dict,
    summary="Listar notas",
    description="Lista notas filtrando por usuario, estado o tag.",
)
def get_note(
    user_id: Optional[str] = Query(default=None),
    status_f: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
):
    try:
        items = list_notes(user_id=user_id, status=status_f, tag=tag)
        return {"note": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron listar las notas: {e}")
