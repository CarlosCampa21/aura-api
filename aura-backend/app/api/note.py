"""
Endpoints para `note` (singular, convención en inglés).
"""
from fastapi import APIRouter, HTTPException, status, Query
from typing import Optional
from app.domain.note.schemas import NoteCreate, NoteOut
from app.repositories.note_repo import insert_note, list_notes


router = APIRouter(prefix="/note", tags=["Note"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
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
        raise HTTPException(status_code=500, detail=f"Insert note failed: {e}")


@router.get("", response_model=dict)
def get_note(
    user_id: Optional[str] = Query(default=None),
    status_f: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
):
    try:
        items = list_notes(user_id=user_id, status=status_f, tag=tag)
        return {"note": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List note failed: {e}")
