# app/api/schedules.py
from fastapi import APIRouter, HTTPException, status, Query
from pydantic import EmailStr
from typing import Optional
from app.domain.schedules.schemas import ScheduleCreate
from app.repositories.schedules_repo import insert_schedule, list_schedules

router = APIRouter(prefix="/schedules", tags=["Schedules"])

@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_schedule(payload: ScheduleCreate):
    try:
        inserted_id = insert_schedule(payload.model_dump(mode="json"))
        return {"message": "ok", "id": inserted_id, "data": payload.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert horario failed: {e}")

@router.get("", response_model=dict)
def get_schedules(usuario_correo: Optional[EmailStr] = Query(default=None)):
    try:
        items = list_schedules(str(usuario_correo) if usuario_correo else None)
        return {"horarios": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query horarios failed: {e}")
