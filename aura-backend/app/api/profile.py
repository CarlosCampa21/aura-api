"""
Endpoints para consultar y actualizar el perfil del usuario autenticado.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from app.services.auth_validator import get_current_user
from app.domain.user.schemas import UserProfileUpdate
from app.repositories.user_repo import update_user_profile

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("", response_model=dict)
def get_my_profile(user=Depends(get_current_user)):
    try:
        return {"profile": user.get("profile") or {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo obtener el perfil: {e}")


@router.patch("", response_model=dict, status_code=status.HTTP_200_OK)
def patch_my_profile(payload: UserProfileUpdate, user=Depends(get_current_user)):
    try:
        data = payload.model_dump(exclude_none=True)
        new_profile = update_user_profile(str(user["_id"]), data)
        return {"message": "ok", "profile": new_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo actualizar el perfil: {e}")

