# app/api/router.py
from fastapi import APIRouter
from app.api import aura, user, subjects, schedules, notes, queries, auth  

api_router = APIRouter()
api_router.include_router(aura.router)
api_router.include_router(user.router)
api_router.include_router(auth.router)
api_router.include_router(subjects.router)
api_router.include_router(schedules.router)
api_router.include_router(notes.router)
api_router.include_router(queries.router) 
