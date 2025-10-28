"""Schemas para endpoints de health/debug."""
from typing import List, Optional
from pydantic import BaseModel


class PingOut(BaseModel):
    message: str


class HealthOut(BaseModel):
    ok: bool


class DebugStatusOut(BaseModel):
    app_name: str
    api_prefix: str
    openai_configured: bool
    ollama_url: str
    ollama_model: str
    ollama_timeout_seconds: int
    ollama_reachable: bool
    ollama_models: Optional[List[str]] = None
    ollama_error: Optional[str] = None


class DebugOllamaOut(BaseModel):
    ok: bool
    response: Optional[str] = None
    error: Optional[str] = None


class DebugNowOut(BaseModel):
    server_now: str
    tz: Optional[str] = None
    user_now: Optional[str] = None

