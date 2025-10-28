# app/main.py
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.infrastructure.db.mongo import init_mongo, db_ready
from app.infrastructure.db.bootstrap import ensure_collections
from app.api.router import api_router

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

# Monta routers
app.include_router(api_router, prefix=settings.api_prefix or "")
