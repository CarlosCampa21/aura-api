# app/infrastructure/db/mongo.py
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from app.core.config import settings
import certifi

_client: MongoClient | None = None
_db = None

def init_mongo():
    """
    Inicializa el cliente y valida conexión (ping).
    Llamar una sola vez en el startup de FastAPI.
    """
    global _client, _db
    uri = settings.mongo_uri
    try:
        # No forzar opciones TLS cuando es SRV (Atlas maneja TLS automáticamente)
        kwargs = dict(serverSelectionTimeoutMS=10000)
        if not uri.startswith("mongodb+srv://"):
            kwargs["tls"] = True
            kwargs["tlsCAFile"] = certifi.where()
            kwargs["tlsAllowInvalidCertificates"] = bool(
                getattr(settings, "mongo_tls_insecure", False)
            )
            kwargs["tlsAllowInvalidHostnames"] = bool(
                getattr(settings, "mongo_tls_allow_invalid_hostnames", False)
            )

        _client = MongoClient(uri, **kwargs)
        _client.admin.command("ping")
        _db = _client[settings.mongo_db]
    except ServerSelectionTimeoutError as e:
        raise RuntimeError(f"Mongo no accesible: {e}")

def get_db():
    """
    Devuelve la referencia a la base de datos.
    Úsalo en repositorios/servicios, no en routers.
    """
    if _db is None:
        raise RuntimeError("Mongo no inicializado. Llama init_mongo() en startup.")
    return _db
