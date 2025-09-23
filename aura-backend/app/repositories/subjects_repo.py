# app/repositories/subjects_repo.py
from typing import Dict, List
from app.infrastructure.db.mongo import get_db

COLLECTION = "materias"

def insert_subject(doc: Dict) -> str:
    db = get_db()
    res = db[COLLECTION].insert_one(dict(doc))
    return str(res.inserted_id)

def list_subjects() -> List[Dict]:
    db = get_db()
    return list(db[COLLECTION].find({}, {"_id": 0}))
