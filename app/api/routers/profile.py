"""Endpoints de perfil del usuario autenticado."""

from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import get_current_user
from app.api.schemas.user import UserProfileUpdate, ProfileOut, ProfileUpdateOut
from app.services import profile_service

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get(
    "",
    response_model=ProfileOut,
    summary="Obtener mi perfil",
    description="Devuelve el perfil del usuario autenticado.",
)
def get_my_profile(user=Depends(get_current_user)) -> ProfileOut:
    try:
        return ProfileOut(profile=profile_service.get_my_profile(user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo obtener el perfil: {e}")


@router.patch(
    "",
    response_model=ProfileUpdateOut,
    status_code=status.HTTP_200_OK,
    summary="Actualizar mi perfil",
    description="Actualiza parcialmente el perfil del usuario autenticado.",
)
def patch_my_profile(payload: UserProfileUpdate, user=Depends(get_current_user)) -> ProfileUpdateOut:
    try:
        data = payload.model_dump(exclude_none=True)
        new_profile = profile_service.update_my_profile(str(user["_id"]), data)
        return ProfileUpdateOut(message="ok", profile=new_profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo actualizar el perfil: {e}")
