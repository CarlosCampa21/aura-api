"""
Esquemas Pydantic para chat conversacional.

Convenciones:
- Campos y colecciones en inglés (snake_case).
- Comentarios en español.
- Timestamps en ISO-8601 UTC (sellados en el repositorio).
"""

from typing import Optional, Literal, List, Dict
from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    """Crear una conversación.

    - `user_id`: ObjectId como string.
    - `title`: opcional; si no se proporciona, se puede generar del primer mensaje.
    - `model`: modelo por defecto usado para la conversación.
    - `settings`: configuración específica del modelo (temperature, etc.).
    - `metadata`: metadatos libres (p. ej., subject_id, tags).
    """

    user_id: Optional[str] = None
    title: Optional[str] = None
    model: Optional[str] = Field(default="gpt-4o-mini")
    settings: Optional[Dict] = None
    metadata: Optional[Dict] = None
    session_id: Optional[str] = None  # modo invitado
    mode: Optional[Literal["auth", "guest"]] = None


class ConversationOut(BaseModel):
    """Salida pública de conversación (sin `_id`)."""

    user_id: Optional[str] = None
    title: str
    status: Literal["active", "archived"]
    model: str
    settings: Optional[Dict] = None
    metadata: Optional[Dict] = None
    last_message_at: str
    created_at: str
    updated_at: str

class MessageCreate(BaseModel):
    """Crear un mensaje dentro de una conversación."""

    conversation_id: str
    user_id: Optional[str] = None
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    attachments: List[str] = Field(default_factory=list)
    session_id: Optional[str] = None


class MessageOut(BaseModel):
    conversation_id: str
    user_id: Optional[str] = None
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    attachments: List[str] = Field(default_factory=list)
    citations: List[Dict] = Field(default_factory=list)
    model_snapshot: Optional[str] = None
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    error: Optional[Dict] = None
    created_at: str
    session_id: Optional[str] = None


class ChatAskPayload(BaseModel):
    """Payload de orquestación de chat (alta de conversación y mensajes)."""

    user_id: Optional[str] = None
    content: str
    conversation_id: Optional[str] = None
    model: Optional[str] = None
    settings: Optional[Dict] = None
    create_if_missing: bool = True
    # Orquestación avanzada
    stream: bool = False
    save_note: bool = False
    note_title: Optional[str] = None
    note_tags: List[str] = Field(default_factory=list)
    session_id: Optional[str] = None  # para modo invitado


class ChatAskOut(BaseModel):
    conversation_id: str
    user_message: MessageOut
    assistant_message: MessageOut
    model: Optional[str] = None
    session_id: Optional[str] = None

