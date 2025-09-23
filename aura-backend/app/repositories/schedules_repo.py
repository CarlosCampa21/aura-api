# app/repositories/schedules_repo.py
from typing import Dict, List, Optional
from app.infrastructure.db.mongo import get_db

COLLECTION = "horarios"

def insert_schedule(doc: Dict) -> str:
    db = get_db()
    data = dict(doc)
    if "usuario_correo" in data:
        data["usuario_correo"] = str(data["usuario_correo"])
    res = db[COLLECTION].insert_one(data)
    return str(res.inserted_id)

def list_schedules(usuario_correo: Optional[str] = None) -> List[Dict]:
    db = get_db()
    filtro: Dict = {}
    if usuario_correo:
        filtro["usuario_correo"] = str(usuario_correo)
    return list(db[COLLECTION].find(filtro, {"_id": 0}))
