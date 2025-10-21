"""
Verificación de ID Tokens de Google.

Usa `google.oauth2.id_token.verify_oauth2_token` con el `google_client_id` configurado
como audiencia. El frontend debe enviar el `id_token` obtenido de Google Sign-In
(One Tap o OAuth).
"""
from typing import Dict, Any

from google.oauth2 import id_token
from google.auth.transport import requests as grequests

from app.core.config import settings


class GoogleTokenError(Exception):
    pass


def verify_id_token(id_token_str: str) -> Dict[str, Any]:
    """
    Verifica un Google ID Token y devuelve sus claims si es válido.
    Requiere `settings.google_client_id` configurado.
    """
    if not settings.google_client_id:
        raise GoogleTokenError("Falta GOOGLE_CLIENT_ID en configuración")
    try:
        req = grequests.Request()
        claims = id_token.verify_oauth2_token(id_token_str, req, settings.google_client_id)
        # `aud` lo valida verify_oauth2_token; aseguramos que sea emitido por cuentas de Google
        if claims.get("iss") not in {"https://accounts.google.com", "accounts.google.com"}:
            raise GoogleTokenError("Emisor no válido")
        return claims
    except Exception as e:
        raise GoogleTokenError(str(e))

