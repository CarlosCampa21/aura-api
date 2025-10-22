"""
Endpoints para chat conversacional (conversations/messages).
"""
from fastapi import APIRouter, HTTPException, status, Query
from typing import Optional
from app.domain.chat.schemas import (
    ConversationCreate,
    ConversationOut,
    MessageCreate,
    MessageOut,
)
from app.repositories.conversations_repo import (
    insert_conversation,
    list_conversations as repo_list_conversations,
)
from app.repositories.messages_repo import (
    insert_message,
    list_messages as repo_list_messages,
)


router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/conversations", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_conversation(payload: ConversationCreate):
    try:
        inserted_id = insert_conversation(payload.model_dump(mode="json"))
        # Echo mínimo; los timestamps reales los define el repo.
        out = ConversationOut(
            user_id=payload.user_id,
            title=payload.title or "",
            status="active",
            model=payload.model or "gpt-4o-mini",
            settings=payload.settings,
            metadata=payload.metadata,
            last_message_at="",
            created_at="",
            updated_at="",
        ).model_dump()
        return {"message": "ok", "id": inserted_id, "data": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert conversation failed: {e}")


@router.get("/conversations", response_model=dict)
def get_conversations(user_id: Optional[str] = Query(default=None), status_f: Optional[str] = Query(default=None)):
    try:
        items = repo_list_conversations(user_id=user_id, status=status_f)
        return {"conversations": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List conversations failed: {e}")


@router.post("/messages", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_message(payload: MessageCreate):
    try:
        inserted_id = insert_message(payload.model_dump(mode="json"))
        out = MessageOut(
            conversation_id=payload.conversation_id,
            user_id=payload.user_id,
            role=payload.role,
            content=payload.content,
            attachments=payload.attachments,
            citations=[],
            model_snapshot=None,
            tokens_input=None,
            tokens_output=None,
            error=None,
            created_at="",
        ).model_dump()
        return {"message": "ok", "id": inserted_id, "data": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert message failed: {e}")


@router.get("/messages", response_model=dict)
def get_messages(
    conversation_id: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
):
    if not conversation_id and not user_id:
        raise HTTPException(status_code=400, detail="conversation_id o user_id es requerido")
    try:
        items = repo_list_messages(conversation_id=conversation_id, user_id=user_id)
        return {"messages": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List messages failed: {e}")

