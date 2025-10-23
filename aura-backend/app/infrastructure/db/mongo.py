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
        # Ajustes conservadores: 15s y CA de certifi incluso con SRV
        kwargs = dict(serverSelectionTimeoutMS=15000)
        if uri.startswith("mongodb+srv://"):
            # SRV ya implica TLS; proveemos CA bundle para robustez
            kwargs["tlsCAFile"] = certifi.where()
        else:
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
        print("[Mongo] Conectado correctamente", flush=True)
    except ServerSelectionTimeoutError as e:
        # No tumbar la app: deja _db en None y loggea
        print(f"[Mongo][WARN] No accesible (timeout): {e}", flush=True)
        _client = None
        _db = None
    except Exception as e:
        print(f"[Mongo][WARN] Error de conexión: {e}", flush=True)
        _client = None
        _db = None

def get_db():
    """
    Devuelve la referencia a la base de datos.
    Úsalo en repositorios/servicios, no en routers.
    """
    if _db is None:
        raise RuntimeError("Mongo no inicializado. Intenta más tarde.")
    return _db

def db_ready() -> bool:
    return _db is not None
