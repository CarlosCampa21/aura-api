# app/main.py
from fastapi import FastAPI, status
import requests
from app.infrastructure.ai.ollama_client import ollama_ask
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.infrastructure.db.mongo import init_mongo, db_ready
from app.infrastructure.db.bootstrap import ensure_collections
from app.api.router import api_router
from zoneinfo import ZoneInfo
from datetime import datetime
from app.infrastructure.db.mongo import get_db

app = FastAPI(title=settings.app_name)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup
@app.on_event("startup")
def on_startup():
    init_mongo()
    # Garantiza colecciones/índices/validadores mínimos si hay conexión
    try:
        if db_ready():
            ensure_collections()
        else:
            print("[Startup][WARN] Mongo no listo; omitiendo ensure_collections()", flush=True)
    except Exception as e:
        # No impedir el arranque si fallan validadores/índices
        print(f"[Startup][WARN] ensure_collections() falló: {e}", flush=True)

# Health / Ping
@app.get("/ping")
def ping():
    return {"message": "pong"}

@app.get("/health", status_code=status.HTTP_200_OK)
def health():
    # Salud básica; si quieres, haz un ping real a Mongo en un servicio dedicado
    return {"ok": True}

# Monta routers
app.include_router(api_router, prefix=settings.api_prefix or "")

# Debug status: revisa configuración y conectividad básica a Ollama
@app.get("/_debug/status", status_code=status.HTTP_200_OK)
def debug_status():
    out = {
        "app_name": settings.app_name,
        "api_prefix": settings.api_prefix,
        "openai_configured": bool(settings.openai_api_key),
        "ollama_url": settings.ollama_url,
        "ollama_model": settings.ollama_model,
        "ollama_timeout_seconds": settings.ollama_timeout_seconds,
    }

    # Probar Ollama /api/tags
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

@app.get("/_debug/ollama", status_code=status.HTTP_200_OK)
def debug_ollama(sample: str = "Hola, ¿quién eres?"):
    """
    Hace una llamada mínima a Ollama usando la misma ruta que usa la app (/api/chat)
    para detectar errores de compatibilidad o de modelo.
    """
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

@app.get("/_debug/now", status_code=status.HTTP_200_OK)
def debug_now(email: str | None = None, tz: str | None = None):
    """
    Devuelve la hora del servidor y, si hay email o tz, la hora resuelta
    para esa zona horaria (usando profile.tz cuando email está presente).
    """
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
    return {"server_now": server_now, "tz": resolved_tz, "user_now": user_now}
