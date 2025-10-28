"""
Endpoints para consultar y actualizar el perfil del usuario autenticado.

- Mantiene el namespace `/profile` como antes.
- La API delega en `services/profile_service.py` para seguir la misma estructura
  de capas que usamos en auth (API delgada, dominio para schemas y servicios
  con la lógica).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import get_current_user
from app.api.schemas.user import UserProfileUpdate
from app.services import profile_service

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("", response_model=dict)
def get_my_profile(user=Depends(get_current_user)):
    try:
        return {"profile": profile_service.get_my_profile(user)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo obtener el perfil: {e}")


@router.patch("", response_model=dict, status_code=status.HTTP_200_OK)
def patch_my_profile(payload: UserProfileUpdate, user=Depends(get_current_user)):
    try:
        data = payload.model_dump(exclude_none=True)
        new_profile = profile_service.update_my_profile(str(user["_id"]), data)
        return {"message": "ok", "profile": new_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo actualizar el perfil: {e}")
