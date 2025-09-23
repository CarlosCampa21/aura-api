# app/api/subjects.py
from fastapi import APIRouter, HTTPException, status
from app.domain.subjects.schemas import SubjectCreate, SubjectOut
from app.repositories.subjects_repo import insert_subject, list_subjects

router = APIRouter(prefix="/subjects", tags=["Subjects"])

@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_subject(payload: SubjectCreate):
    try:
        inserted_id = insert_subject(payload.model_dump())
        return {
            "message": "ok",
            "id": inserted_id,
            "data": SubjectOut(**payload.model_dump()).model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert materia failed: {e}")

@router.get("", response_model=dict)
def get_subjects():
    try:
        return {"materias": list_subjects()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query materias failed: {e}")
