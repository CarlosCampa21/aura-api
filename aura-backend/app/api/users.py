# app/api/users.py
from fastapi import APIRouter, HTTPException, status
from app.domain.users.schemas import UserCreate, UserOut
from app.repositories.users_repo import insert_user, list_users

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_user(payload: UserCreate):
    """
    Crea un usuario.
    """
    try:
        inserted_id = insert_user(payload.model_dump(mode="json"))
        return {
            "message": "ok",
            "id": inserted_id,
            "data": UserOut(**payload.model_dump()).model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert usuario failed: {e}")

@router.get("", response_model=dict)
def get_users():
    """
    Lista usuarios (sin _id).
    """
    try:
        return {"usuarios": list_users()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query usuarios failed: {e}")
