"""
Rutas para la entidad `user` (singular).
"""
from fastapi import APIRouter, HTTPException, status
from app.domain.user.schemas import UserCreate
from app.repositories.user_repo import insert_user, list_users

router = APIRouter(prefix="/user", tags=["User"])

@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_user(payload: UserCreate):
    """
    Crea un usuario.
    """
    try:
        inserted_id = insert_user(payload.model_dump(mode="json"))
        return {"message": "ok", "id": inserted_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert user failed: {e}")

@router.get("", response_model=dict)
def get_users():
    """
    Lista user (sin _id).
    """
    try:
        return {"user": list_users()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query user failed: {e}")
