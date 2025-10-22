# app/api/router.py
from fastapi import APIRouter
from app.api import aura, subjects, schedules, auth, profile, chat, note  

api_router = APIRouter()
api_router.include_router(aura.router)
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(subjects.router)
api_router.include_router(schedules.router)
api_router.include_router(chat.router)
api_router.include_router(note.router)
