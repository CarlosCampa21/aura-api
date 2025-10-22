"""
Repositorios para catálogos académicos: department, program, period, course.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.infrastructure.db.mongo import get_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Department
def insert_department(doc: Dict[str, Any]) -> str:
    db = get_db()
    data = dict(doc)
    now = _now_iso()
    data.setdefault("created_at", now)
    data["updated_at"] = now
    res = db["department"].insert_one(data)
    return str(res.inserted_id)


def list_departments() -> List[Dict[str, Any]]:
    db = get_db()
    docs = list(db["department"].find({}).sort("code", 1))
    out: List[Dict[str, Any]] = []
    for d in docs:
        d = dict(d)
        d.pop("_id", None)
        out.append(d)
    return out


# Program
def insert_program(doc: Dict[str, Any]) -> str:
    db = get_db()
    data = dict(doc)
    now = _now_iso()
    data.setdefault("created_at", now)
    data["updated_at"] = now
    res = db["program"].insert_one(data)
    return str(res.inserted_id)


def list_programs(department_code: Optional[str] = None) -> List[Dict[str, Any]]:
    db = get_db()
    q: Dict[str, Any] = {}
    if department_code:
        q["department_code"] = department_code
    docs = list(db["program"].find(q).sort("code", 1))
    out: List[Dict[str, Any]] = []
    for d in docs:
        d = dict(d)
        d.pop("_id", None)
        out.append(d)
    return out


# Period
def insert_period(doc: Dict[str, Any]) -> str:
    db = get_db()
    data = dict(doc)
    now = _now_iso()
    data.setdefault("created_at", now)
    data["updated_at"] = now
    res = db["period"].insert_one(data)
    return str(res.inserted_id)


def list_periods(status: Optional[str] = None) -> List[Dict[str, Any]]:
    db = get_db()
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    docs = list(db["period"].find(q).sort([("year", -1), ("term", -1)]))
    out: List[Dict[str, Any]] = []
    for d in docs:
        d = dict(d)
        d.pop("_id", None)
        out.append(d)
    return out


# Course
def insert_course(doc: Dict[str, Any]) -> str:
    db = get_db()
    data = dict(doc)
    now = _now_iso()
    data.setdefault("created_at", now)
    data["updated_at"] = now
    res = db["course"].insert_one(data)
    return str(res.inserted_id)


def list_courses() -> List[Dict[str, Any]]:
    db = get_db()
    docs = list(db["course"].find({}).sort("name", 1))
    out: List[Dict[str, Any]] = []
    for d in docs:
        d = dict(d)
        d.pop("_id", None)
        out.append(d)
    return out

