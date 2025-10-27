"""
Rate limit muy simple en memoria (por IP + ruta).
"""
from time import time
from typing import Dict, Tuple

BUCKET: Dict[Tuple[str, str], list[float]] = {}


def allow(key: Tuple[str, str], limit: int = 5, window_seconds: int = 60) -> bool:
    now = time()
    q = BUCKET.setdefault(key, [])
    # elimina timestamps fuera de ventana
    q[:] = [t for t in q if now - t < window_seconds]
    if len(q) >= limit:
        return False
    q.append(now)
    return True

