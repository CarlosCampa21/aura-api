"""
Rutas para la entidad `user` (singular).

Nota: La creación/registro de usuarios se realiza exclusivamente vía `/auth/register`.
Este módulo expone solo lectura para evitar duplicar flujos de registro.
"""
from fastapi import APIRouter, HTTPException, status
from app.services import user_service

router = APIRouter(prefix="/user", tags=["User"])


@router.get("", response_model=dict)
def get_users():
    """
    Lista usuarios (sin campos sensibles y sin `_id`).
    """
    try:
        return {"user": user_service.list_users()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query user failed: {e}")
