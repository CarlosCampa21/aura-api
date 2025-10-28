"""Health y debug (sin auth), salidas simples."""
from fastapi import APIRouter, status
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

from app.core.config import settings
from app.infrastructure.db.mongo import get_db
from app.infrastructure.ai.ollama_client import ollama_ask


router = APIRouter(tags=["Health"])  # no prefix to keep paths stable


@router.get(
    "/ping",
    summary="Ping básico",
    description="Prueba de vida del servicio (sin auth).",
)
def ping():
    return {"message": "pong"}


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Salud básica",
    description="Devuelve ok=true si la app está arriba (sin ping a dependencias).",
)
def health():
    return {"ok": True}


@router.get(
    "/_debug/status",
    status_code=status.HTTP_200_OK,
    summary="Estado de configuración y Ollama",
    description="Muestra flags de config y prueba /api/tags de Ollama si está configurado.",
)
def debug_status():
    out = {
        "app_name": settings.app_name,
        "api_prefix": settings.api_prefix,
        "openai_configured": bool(settings.openai_api_key),
        "ollama_url": settings.ollama_url,
        "ollama_model": settings.ollama_model,
        "ollama_timeout_seconds": settings.ollama_timeout_seconds,
    }

    try:
        r = requests.get(f"{settings.ollama_url}/api/tags", timeout=3)
        r.raise_for_status()
        data = r.json() if r.content else {}
        out["ollama_reachable"] = True
        out["ollama_models"] = [m.get("name") for m in data.get("models", [])]
    except Exception as e:
        out["ollama_reachable"] = False
        out["ollama_error"] = str(e)

    return out


@router.get(
    "/_debug/ollama",
    status_code=status.HTTP_200_OK,
    summary="Ping a Ollama con prompt de ejemplo",
    description="Llama a Ollama usando el mismo cliente que la app.",
)
def debug_ollama(sample: str = "Hola, ¿quién eres?"):
    try:
        text = ollama_ask(
            "Eres un asistente de prueba.",
            sample,
            temperature=0.1,
            timeout=settings.ollama_timeout_seconds,
        )
        return {"ok": True, "response": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get(
    "/_debug/now",
    status_code=status.HTTP_200_OK,
    summary="Hora del servidor y resuelta",
    description="Devuelve la hora del servidor y, si hay email/tz, la hora en esa zona.",
)
def debug_now(email: str | None = None, tz: str | None = None):
    server_now = datetime.now().isoformat()
    resolved_tz = tz
    user_now = None
    if email:
        try:
            u = get_db()["user"].find_one({"email": email}, {"profile": 1}) or {}
            p = (u or {}).get("profile") or {}
            resolved_tz = resolved_tz or p.get("tz")
        except Exception:
            pass
    try:
        if resolved_tz:
            user_now = datetime.now(ZoneInfo(resolved_tz)).isoformat()
    except Exception as e:
        user_now = f"Zona horaria inválida: {resolved_tz} ({e})"
    return {"server_now": server_now, "tz": resolved_tz, "user_now": user_now}
