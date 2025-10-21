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

    # Auth / JWT
    jwt_secret: str = "change-me-dev-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Google OAuth
    google_client_id: str | None = None

    # Email / SMTP (para verificación de correo)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "AURA"
    smtp_use_tls: bool = True

    # Link base para verificación de email (se le concatena el token)
    email_verify_link_base: str = "http://localhost:8000/api/auth/verify-email?token="

    class Config:
        env_file = str(ENV_FILE)   # carga variables del backend, sin depender del CWD

settings = Settings()
