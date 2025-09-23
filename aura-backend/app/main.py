# app/main.py
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.infrastructure.db.mongo import init_mongo
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
    