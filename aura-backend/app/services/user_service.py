"""
Servicios para la entidad `user`.

Mantienen la lógica de negocio fuera de la capa API. Por ahora solo lectura,
ya que el registro/creación se hace exclusivamente vía `/auth/register`.
"""

from typing import Dict, Any, List
from app.repositories.user_repo import list_users as _list_users


def list_users() -> List[Dict[str, Any]]:
    """Lista de usuarios sin exponer campos sensibles."""
    return _list_users()
