"""Entrada principal de la app FastAPI (configura middlewares, excepciones y routers)."""
from fastapi import FastAPI
from app.core.config import settings
from app.infrastructure.db.mongo import init_mongo, db_ready
from app.infrastructure.db.bootstrap import ensure_collections
from app.api.router import api_router
from app.core.logging import setup_logging
from app.core.middleware import add_middlewares
from app.core.exceptions import register_exception_handlers
import logging

_log = logging.getLogger("aura.startup")

setup_logging()
app = FastAPI(title=settings.app_name)

add_middlewares(app)
register_exception_handlers(app)

# Startup
@app.on_event("startup")
def on_startup():
    init_mongo()
    # Garantiza colecciones/índices/validadores mínimos si hay conexión
    try:
        if db_ready():
            ensure_collections()
        else:
            _log.warning("Mongo no listo; omitiendo ensure_collections()")
    except Exception as e:
        # No impedir el arranque si fallan validadores/índices
        _log.warning("ensure_collections() falló: %s", e)

# Monta routers bajo el prefijo configurado
app.include_router(api_router, prefix=settings.api_prefix_normalized or (settings.api_prefix or ""))
