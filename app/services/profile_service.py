"""Servicios de perfil de usuario.

Mantiene la API delgada y centraliza la actualización del subdocumento `profile`.
"""

from typing import Dict, Any
from app.repositories.user_repo import update_user_profile as _update_user_profile


def get_my_profile(user_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Extrae el subdocumento `profile` del usuario autenticado."""
    return (user_doc or {}).get("profile") or {}


def update_my_profile(user_id: str, partial_update: Dict[str, Any]) -> Dict[str, Any]:
    """Actualiza parcialmente el perfil del usuario y devuelve el perfil actualizado."""
    return _update_user_profile(user_id, partial_update)
