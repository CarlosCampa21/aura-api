# app/repositories/notes_repo.py
from typing import Dict, List, Optional
from datetime import datetime
from app.infrastructure.db.mongo import get_db

COLLECTION = "notas"

def insert_note(doc: Dict) -> str:
    db = get_db()
    data = dict(doc)
    # normaliza correo a str
    if "usuario_correo" in data:
        data["usuario_correo"] = str(data["usuario_correo"])
    # created_at por defecto
    data["created_at"] = data.get("created_at") or datetime.utcnow().isoformat()
    res = db[COLLECTION].insert_one(data)
    return str(res.inserted_id)

def list_notes(usuario_correo: Optional[str] = None) -> List[Dict]:
    db = get_db()
    filtro: Dict = {}
    if usuario_correo:
        filtro["usuario_correo"] = str(usuario_correo)
    return list(db[COLLECTION].find(filtro, {"_id": 0}))
