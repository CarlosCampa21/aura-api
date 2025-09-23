# app/infrastructure/db/mongo.py
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from app.core.config import settings

_client: MongoClient | None = None
_db = None

def init_mongo():
    """
    Inicializa el cliente y valida conexión (ping).
    Llamar una sola vez en el startup de FastAPI.
    """
    global _client, _db
    try:
        _client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=3000)
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
