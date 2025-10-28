"""
Modelo Pydantic para documentos de la colección `refresh_token`.
"""
from typing import Optional
from pydantic import BaseModel


class RefreshTokenModel(BaseModel):
    user_id: str  # ObjectId en string
    token_hash: str
    family_id: str
    rotation_parent_id: Optional[str] = None  # ObjectId en string o None
    device_id: str
    ip: str
    user_agent: str
    created_at: str  # ISO-8601
    expires_at: str  # ISO-8601
    revoked_at: Optional[str] = None  # ISO-8601 o None
    revoked_reason: Optional[str] = None

