"""
Rate limit muy simple en memoria (por identificador + ruta).

Uso típico:
- Invitado por sesión: allow((session_id, "/chat/ask"), limit=10, window_seconds=60)
- Usuario autenticado: allow((f"user:{user_id}:{ip}", "/chat/ask"), limit=30, window_seconds=60)
"""
from time import time
from typing import Dict, Tuple

BUCKET: Dict[Tuple[str, str], list[float]] = {}


def allow(key: Tuple[str, str], limit: int = 5, window_seconds: int = 60) -> bool:
    """Devuelve True si se permite la acción y registra el intento.

    key: (identificador, ruta)
    limit: máximo de intentos dentro de la ventana
    window_seconds: ventana de tiempo en segundos
    """
    now = time()
    q = BUCKET.setdefault(key, [])
    # elimina timestamps fuera de ventana
    q[:] = [t for t in q if now - t < window_seconds]
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def allow_key(route: str, identifier: str, limit: int = 5, window_seconds: int = 60) -> bool:
    """Atajo para construir la clave como (identificador, ruta)."""
    return allow((identifier, route), limit=limit, window_seconds=window_seconds)


def reset() -> None:
    """Limpia el bucket (útil en tests o reinicios)."""
    BUCKET.clear()
