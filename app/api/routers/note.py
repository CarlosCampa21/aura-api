"""
Endpoints para `note` (singular, convención en inglés).
"""
from fastapi import APIRouter, HTTPException, status, Query
from typing import Optional
from app.api.schemas.note import NoteCreate, NoteOut, NoteCreateResponse, NoteListOut
from app.services.note_service import insert_note, list_notes


router = APIRouter(prefix="/note", tags=["Note"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=NoteCreateResponse,
    summary="Crear nota",
    description="Crea una nota del usuario con tags y relación opcional a una conversación.",
)
def create_note(payload: NoteCreate) -> NoteCreateResponse:
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
        return NoteCreateResponse(message="ok", id=inserted_id, data=NoteOut(**out))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert note failed: {e}")


@router.get(
    "",
    response_model=NoteListOut,
    summary="Listar notas",
    description="Lista notas del usuario con filtros opcionales (status, tag).",
)
def get_note(
    user_id: Optional[str] = Query(default=None),
    status_f: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
):
    try:
        items = list_notes(user_id=user_id, status=status_f, tag=tag)
        return NoteListOut(note=[NoteOut(**i) for i in items])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List note failed: {e}")
