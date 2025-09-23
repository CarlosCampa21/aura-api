# app/repositories/queries_repo.py
from typing import Dict, List, Optional
from datetime import datetime
from app.infrastructure.db.mongo import get_db

COLLECTION = "consultas"

def insert_query(doc: Dict) -> str:
    db = get_db()
    data = dict(doc)
    # normaliza correo y timestamp
    if "usuario_correo" in data:
        data["usuario_correo"] = str(data["usuario_correo"])
    data["ts"] = data.get("ts") or datetime.utcnow().isoformat()
    res = db[COLLECTION].insert_one(data)
    return str(res.inserted_id)

def list_queries(usuario_correo: Optional[str] = None) -> List[Dict]:
    db = get_db()
    filtro: Dict = {}
    if usuario_correo:
        filtro["usuario_correo"] = str(usuario_correo)
    return list(db[COLLECTION].find(filtro, {"_id": 0}))
