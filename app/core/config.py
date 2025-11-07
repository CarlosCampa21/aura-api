"""Configuración central de la aplicación (Pydantic Settings).

- Carga variables desde .env en la raíz del backend.
- Agrupa ajustes por área: App, CORS, Mongo, Auth/JWT, OpenAI/Ollama, Email, Chat.
"""
from pydantic_settings import BaseSettings
from pydantic import AliasChoices, Field
try:
    # pydantic-settings v2 style
    from pydantic_settings import SettingsConfigDict  # type: ignore
except Exception:  # pragma: no cover
    SettingsConfigDict = None  # type: ignore
from pathlib import Path

# Resuelve el .env ubicado en la raíz del backend (independiente del CWD)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

class Settings(BaseSettings):
    """Conjunto de variables de configuración con valores por defecto razonables.

    Nota: los valores pueden sobreescribirse vía variables de entorno (.env).
    """
    # App
    app_name: str = "Aura API (Académica)"
    api_prefix: str = "/api"

    # CORS (para Vite/React en localhost)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "https://aura-ai-client.vercel.app"]
    cors_allow_any: bool = False  # Permite todos los orígenes (usa con cuidado)

    # Mongo
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "aura_db"
    # TLS relax options (dev only)
    mongo_tls_insecure: bool = False  # allows invalid certs
    mongo_tls_allow_invalid_hostnames: bool = False

    # Auth / JWT
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # OpenAI
    openai_api_key: str | None = None
    openai_model_primary: str = "gpt-4o-mini"
    openai_model_fallback: str = "gpt-4o-mini"
    # Embeddings (RAG)
    # Nota: para Atlas Vector Search con text-embedding-3-small (1536 dims)
    openai_embeddings_model: str = "text-embedding-3-small"
    openai_embeddings_dims: int = 1536

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: int = 120
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

    # Verificación por código (OTP) y link base
    email_code_expire_minutes: int = 10
    email_verify_link_base: str = "http://localhost:8000/api/auth/verify-email?token="

    # Chat limits / rate limit (configurable)
    chat_guest_rate_per_min: int = 10
    chat_auth_rate_per_min: int = 30
    chat_guest_stream_rate_per_min: int = 8
    chat_auth_stream_rate_per_min: int = 20
    chat_stream_chunk_chars: int = Field(
        400,
        validation_alias=AliasChoices("AURA_CHAT_STREAM_CHUNK", "CHAT_STREAM_CHUNK"),
    )
    chat_stream_single_event: bool = Field(
        True,
        validation_alias=AliasChoices("AURA_CHAT_STREAM_SINGLE", "CHAT_STREAM_SINGLE"),
        description="Si es True, el endpoint /chat/ask/stream envía toda la respuesta en un solo evento SSE",
    )
    chat_prompt_max_chars_guest: int = 800
    chat_prompt_max_chars_auth: int = 4000

    # Chat sampling (configurable vía .env)
    chat_temperature: float = Field(
        0.6,
        validation_alias=AliasChoices("AURA_CHAT_TEMPERATURE", "CHAT_TEMPERATURE"),
    )
    chat_top_p: float = Field(
        0.9,
        validation_alias=AliasChoices("AURA_CHAT_TOP_P", "CHAT_TOP_P"),
    )
    chat_presence_penalty: float = Field(
        0.1,
        validation_alias=AliasChoices("AURA_CHAT_PRESENCE", "CHAT_PRESENCE"),
    )
    chat_frequency_penalty: float = Field(
        0.0,
        validation_alias=AliasChoices("AURA_CHAT_FREQUENCY", "CHAT_FREQUENCY"),
    )

    # RAG sampling
    rag_temperature: float = Field(
        0.6,
        validation_alias=AliasChoices("AURA_RAG_TEMPERATURE", "RAG_TEMPERATURE"),
    )

    # RAG defaults
    rag_snippets_per_doc: int = Field(
        3,
        validation_alias=AliasChoices("AURA_RAG_SNIPPETS_PER_DOC", "RAG_SNIPPETS_PER_DOC"),
    )
    rag_k_default: int = Field(
        10,
        validation_alias=AliasChoices("AURA_RAG_K", "RAG_K"),
    )

    # Chat history window (n últimos mensajes)
    chat_history_n: int = Field(
        8,
        validation_alias=AliasChoices("AURA_CHAT_HISTORY_N", "CHAT_HISTORY_N"),
    )

    # Chat follow‑ups (preguntas al final)
    chat_followups_enabled: bool = Field(
        False,  # desactivado por defecto
        validation_alias=AliasChoices("AURA_CHAT_FOLLOWUPS", "CHAT_FOLLOWUPS"),
    )

    # Storage (R2)
    storage_provider: str | None = None  # e.g., "r2"
    r2_bucket: str | None = None
    r2_endpoint: str | None = None
    r2_region: str = "auto"
    r2_access_key: str | None = None
    r2_secret_key: str | None = None
    r2_public_base_url: str | None = None
    
    # --- Utilidades derivadas / helpers ---
    @property
    def api_prefix_normalized(self) -> str:
        """Devuelve `api_prefix` con formato consistente.

        - Siempre inicia con '/'
        - Sin '/' final (excepto cuando es solo '/')
        - Si está vacío, devuelve ""
        """
        pref = (self.api_prefix or "").strip()
        if not pref:
            return ""
        if not pref.startswith('/'):
            pref = '/' + pref
        if len(pref) > 1 and pref.endswith('/'):
            pref = pref[:-1]
        return pref

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def ollama_configured(self) -> bool:
        return bool(self.ollama_url and self.ollama_model)

    def email_verify_link(self, token: str) -> str:
        """Construye el link de verificación de email a partir del base configurado."""
        return f"{self.email_verify_link_base}{token}"
    # pydantic-settings configuration (v2)
    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(
            env_file=str(ENV_FILE),
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="ignore",  # no fallar si hay variables no usadas
        )
    else:
        # Back-compat for older pydantic-settings
        class Config:  # type: ignore
            env_file = str(ENV_FILE)
            case_sensitive = False


settings = Settings()
