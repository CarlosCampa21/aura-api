# app/repositories/users_repo.py
from typing import List, Dict
from app.infrastructure.db.mongo import get_db

COLLECTION = "usuarios"

def insert_user(doc: Dict) -> str:
    """
    Inserta un usuario y retorna el string del inserted_id.
    Normaliza el correo a str por si viene como EmailStr.
    """
    db = get_db()
    doc = dict(doc)  # copia defensiva
    if "correo" in doc:
        doc["correo"] = str(doc["correo"])
    res = db[COLLECTION].insert_one(doc)
    return str(res.inserted_id)

def list_users() -> List[Dict]:
    """
    Retorna usuarios sin _id para respuesta limpia.
    """
    db = get_db()
    return list(db[COLLECTION].find({}, {"_id": 0}))
