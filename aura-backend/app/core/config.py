# app/core/config.py
from pydantic_settings import BaseSettings
from pathlib import Path

# Resolve the .env located at the backend root regardless of CWD
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

class Settings(BaseSettings):
    # App
    app_name: str = "Aura API (Académica)"
    api_prefix: str = "/api"

    # CORS (para Vite/React en localhost)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Mongo
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "aura_db"

    # OpenAI
    openai_api_key: str | None = None
    openai_model_primary: str = "gpt-5-nano"
    openai_model_fallback: str = "gpt-4o-mini"

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: int = 120

    class Config:
        env_file = str(ENV_FILE)   # carga variables del backend, sin depender del CWD

settings = Settings()
