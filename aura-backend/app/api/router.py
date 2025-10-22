# app/api/router.py
from fastapi import APIRouter
from app.api import aura, auth, profile, chat, note, academics  

api_router = APIRouter()
api_router.include_router(aura.router)
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(chat.router)
api_router.include_router(note.router)
api_router.include_router(academics.router)
