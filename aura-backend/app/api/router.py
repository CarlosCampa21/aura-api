# app/api/router.py
from fastapi import APIRouter
from app.api import aura, users, subjects, schedules, notes, queries  # + queries

api_router = APIRouter()
api_router.include_router(aura.router)
api_router.include_router(users.router)
api_router.include_router(subjects.router)
api_router.include_router(schedules.router)
api_router.include_router(notes.router)
api_router.include_router(queries.router)   # <-- nuevo
