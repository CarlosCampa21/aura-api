# app/api/notes.py
from fastapi import APIRouter, HTTPException, status, Query
from pydantic import EmailStr
from typing import Optional
from app.domain.notes.schemas import NoteCreate, NoteOut
from app.repositories.notes_repo import insert_note, list_notes

router = APIRouter(prefix="/notes", tags=["Notes"])

@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_note(payload: NoteCreate):
    try:
        inserted_id = insert_note(payload.model_dump(mode="json"))
        # Ensambla salida
        out = NoteOut(
            **{
                **payload.model_dump(),
                "usuario_correo": str(payload.usuario_correo),
                "created_at": payload.created_at or "",
            }
        ).model_dump()
        # Si created_at venía vacío, en repo se generó; no lo conocemos aquí.
        # Opcionalmente podrías leer de DB, pero lo dejamos simple.
        return {"message": "ok", "id": inserted_id, "data": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert nota failed: {e}")

@router.get("", response_model=dict)
def get_notes(usuario_correo: Optional[EmailStr] = Query(default=None)):
    try:
        items = list_notes(str(usuario_correo) if usuario_correo else None)
        return {"notas": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query notas failed: {e}")
