"""Cliente MongoDB asíncrono (Motor) y helpers para GridFS.

Se usa sólo en las rutas que necesitan streaming de binarios (p.ej. imágenes/PDF)
sin migrar todo el backend a async.
"""
from __future__ import annotations

import certifi
import logging
from typing import Optional

from app.core.config import settings
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket

_log = logging.getLogger("aura.mongo.async")

_aclient: Optional[AsyncIOMotorClient] = None
_adb: Optional[AsyncIOMotorDatabase] = None
_bucket: Optional[AsyncIOMotorGridFSBucket] = None


def _build_async_client() -> AsyncIOMotorClient:
    uri = settings.mongo_uri
    kwargs = dict(serverSelectionTimeoutMS=15000)
    # Mantiene la lógica TLS similar al cliente sync
    if uri.startswith("mongodb+srv://"):
        kwargs["tlsCAFile"] = certifi.where()
    else:
        kwargs["tls"] = True
        kwargs["tlsCAFile"] = certifi.where()
        if getattr(settings, "mongo_tls_insecure", False):
            kwargs["tlsAllowInvalidCertificates"] = True
        if getattr(settings, "mongo_tls_allow_invalid_hostnames", False):
            kwargs["tlsAllowInvalidHostnames"] = True
    return AsyncIOMotorClient(uri, **kwargs)


def get_async_db() -> AsyncIOMotorDatabase:
    """Devuelve la DB asíncrona; inicializa lazy un único cliente/bd."""
    global _aclient, _adb
    if _adb is None:
        _aclient = _aclient or _build_async_client()
        _adb = _aclient[settings.mongo_db]
        _log.info("Motor listo (db async inicializada)")
    return _adb


def get_gridfs_bucket() -> AsyncIOMotorGridFSBucket:
    """Bucket GridFS asíncrono para binarios grandes (imágenes, PDFs)."""
    global _bucket
    if _bucket is None:
        _bucket = AsyncIOMotorGridFSBucket(get_async_db())
    return _bucket

