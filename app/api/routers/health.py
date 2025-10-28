"""Health y debug (sin auth), salidas tipadas y estables."""
from fastapi import APIRouter, status
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

from app.core.config import settings
from app.infrastructure.db.mongo import get_db
from app.infrastructure.ai.ollama_client import ollama_ask
from app.api.schemas.health import PingOut, HealthOut, DebugStatusOut, DebugOllamaOut, DebugNowOut


router = APIRouter(tags=["Health"])  # no prefix to keep paths stable


@router.get("/ping", response_model=PingOut, summary="Ping básico")
def ping() -> PingOut:
    return PingOut(message="pong")


@router.get("/health", status_code=status.HTTP_200_OK, response_model=HealthOut, summary="Salud básica")
def health() -> HealthOut:
    return HealthOut(ok=True)


@router.get("/_debug/status", status_code=status.HTTP_200_OK, response_model=DebugStatusOut, summary="Estado de configuración y Ollama")
def debug_status() -> DebugStatusOut:
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

    return DebugStatusOut(**out)


@router.get("/_debug/ollama", status_code=status.HTTP_200_OK, response_model=DebugOllamaOut, summary="Ping a Ollama con prompt de ejemplo")
def debug_ollama(sample: str = "Hola, ¿quién eres?") -> DebugOllamaOut:
    try:
        text = ollama_ask(
            "Eres un asistente de prueba.",
            sample,
            temperature=0.1,
            timeout=settings.ollama_timeout_seconds,
        )
        return DebugOllamaOut(ok=True, response=text)
    except Exception as e:
        return DebugOllamaOut(ok=False, error=str(e))


@router.get("/_debug/now", status_code=status.HTTP_200_OK, response_model=DebugNowOut, summary="Hora del servidor y resuelta")
def debug_now(email: str | None = None, tz: str | None = None) -> DebugNowOut:
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
        user_now = f"Invalid tz: {resolved_tz} ({e})"
    return DebugNowOut(server_now=server_now, tz=resolved_tz, user_now=user_now)
