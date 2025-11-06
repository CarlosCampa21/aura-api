"""
Endpoints para chat conversacional (conversations/messages).
"""
from fastapi import APIRouter, HTTPException, status, Query, Header, Request, UploadFile, File, Form
import logging
from typing import Optional
from app.api.schemas.chat import (
    ConversationCreate,
    ConversationOut,
    MessageCreate,
    MessageOut,
    ChatAskPayload,
    ChatAskOut,
)
from app.repositories.conversations_repo import (
    insert_conversation,
    list_conversations as repo_list_conversations,
    get_conversation as repo_get_conversation,
    update_conversation_metadata_fields as repo_update_conv_meta_fields,
    delete_conversation as repo_delete_conversation,
)
from app.repositories.messages_repo import (
    insert_message,
    list_messages as repo_list_messages,
    delete_by_conversation as repo_delete_msgs_by_conv,
)
from app.repositories.files_repo_r2 import upload_uploadfile_to_r2
from app.repositories.auth_repo import get_user_by_id
from app.services.note_service import insert_note as insert_note_doc
from fastapi.responses import StreamingResponse
from app.core.config import settings
from app.core import rate_limit
from app.api.deps import get_current_user_loose as get_current_user
from time import monotonic
from app.services import ask_service


router = APIRouter(prefix="/chat", tags=["Chat"])
_log = logging.getLogger("aura.chat")


@router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
    summary="Crear conversación",
    description="Crea una conversación y devuelve datos base (sin _id expuesto).",
)
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
        raise HTTPException(status_code=500, detail=f"No se pudo crear la conversación: {e}")


@router.get(
    "/conversations",
    response_model=dict,
    summary="Listar conversaciones",
    description="Lista conversaciones por usuario/estado/sesión (no expone _id).",
)
def get_conversations(user_id: Optional[str] = Query(default=None), status_f: Optional[str] = Query(default=None), session_id: Optional[str] = Query(default=None)):
    try:
        items = repo_list_conversations(user_id=user_id, status=status_f, session_id=session_id)
        return {"conversations": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron listar las conversaciones: {e}")


@router.post(
    "/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
    summary="Crear mensaje",
    description="Inserta un mensaje dentro de una conversación.",
)
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
        raise HTTPException(status_code=500, detail=f"No se pudo crear el mensaje: {e}")


@router.post(
    "/messages/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
    summary="Subir archivo y crear mensaje",
    description="Sube un archivo (imagen/PDF) a Cloudflare R2 y crea un mensaje de usuario con ese adjunto.",
)
async def create_message_with_upload(
    conversation_id: str = Form(...),
    user_id: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
    file: UploadFile = File(...),
):
    try:
        async def _chunks():
            size = 256 * 1024
            while True:
                data = await file.read(size)
                if not data:
                    break
                yield data

        # Sube a R2 y obten la URL pública
        attachment_ref = await upload_uploadfile_to_r2(file, prefix="chat/")
        inserted_id = insert_message({
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": "user",
            "content": (file.filename or "Archivo adjunto"),
            "attachments": [attachment_ref],
            "session_id": session_id,
        })

        out = MessageOut(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=(file.filename or "Archivo adjunto"),
            attachments=[attachment_ref],
            citations=[],
            model_snapshot=None,
            tokens_input=None,
            tokens_output=None,
            error=None,
            created_at="",
            session_id=session_id,
        ).model_dump()

        return {"message": "ok", "id": inserted_id, "data": out, "url": attachment_ref}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo subir/crear el mensaje: {e}")


@router.get(
    "/messages",
    response_model=dict,
    summary="Listar mensajes",
    description="Lista mensajes por conversación, usuario o sesión.",
)
def get_messages(
    conversation_id: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
):
    if not conversation_id and not user_id and not session_id:
        raise HTTPException(status_code=400, detail="conversation_id, user_id o session_id es requerido")
    try:
        items = repo_list_messages(conversation_id=conversation_id, user_id=user_id, session_id=session_id)
        return {"messages": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron listar los mensajes: {e}")


@router.delete(
    "/conversations/{conversation_id}",
    response_model=dict,
    summary="Eliminar conversación",
    description="Elimina una conversación y sus mensajes asociados.",
)
def delete_conversation(conversation_id: str, request: Request, x_session_id: Optional[str] = Header(default=None), session_id: Optional[str] = Query(default=None)):
    """Elimina una conversación con validación básica de propiedad (usuario o sesión).

    - Si la conversación tiene `user_id`, requiere Authorization y que coincida.
    - Si es de invitado (sin `user_id`), requiere `X-Session-Id` o `session_id` que coincida.
    """
    try:
        conv = repo_get_conversation(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Validación de propiedad
        owner_user_id = (conv.get("user_id") or "").strip()
        conv_session_id = (conv.get("session_id") or "").strip()

        if owner_user_id:
            # Requiere auth y coincidencia
            auth_header = request.headers.get("authorization")
            current = get_current_user(authorization=auth_header)
            if str(current.get("_id")) != str(owner_user_id):
                raise HTTPException(status_code=403, detail="No autorizado para eliminar esta conversación")
        else:
            # Invitado: usa session id
            sid = session_id or x_session_id
            if not sid or str(sid) != str(conv_session_id):
                raise HTTPException(status_code=403, detail="Falta o no coincide session_id para eliminar esta conversación")

        # Elimina mensajes y conversación
        deleted_msgs = repo_delete_msgs_by_conv(conversation_id)
        deleted_conv = repo_delete_conversation(conversation_id)

        return {"deleted": {"conversation": deleted_conv, "messages": deleted_msgs}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo eliminar la conversación: {e}")


@router.post(
    "/ask",
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
    summary="Preguntar (tool-calling + LLM)",
    description="Orquesta tools (horario/hora) y genera respuesta del asistente.",
)
def chat_ask(payload: ChatAskPayload, request: Request, x_session_id: Optional[str] = Header(default=None)):
    """
    Orquesta la interacción de chat:
      - Crea conversación si falta (opcional)
      - Inserta mensaje del usuario
      - Genera respuesta con IA (usa contexto académico del usuario)
      - Inserta mensaje del asistente
      - Devuelve ambos mensajes y el id de la conversación
    """
    try:
        t0 = monotonic()
        conversation_id = payload.conversation_id
        # Determina modelo efectivo
        effective_model = payload.model or (settings.openai_model_primary if settings.openai_api_key else f"ollama:{settings.ollama_model}")
        # Guest/Auth mode
        user = None
        # Si se envía user_id, requiere Auth y coincidencia
        if payload.user_id:
            auth_header = request.headers.get("authorization")
            current = get_current_user(authorization=auth_header)
            if str(current.get("_id")) != str(payload.user_id):
                raise HTTPException(status_code=403, detail="user_id no coincide con el token")
            user = current
        mode = "auth" if user else "guest"
        session_id = payload.session_id or x_session_id
        if mode == "guest":
            # Rate limit más estricto y session id requerido
            if not session_id:
                # permite operar, pero sugiere al front guardarlo
                import uuid
                session_id = str(uuid.uuid4())
            if not rate_limit.allow((session_id, "/chat/ask"), limit=settings.chat_guest_rate_per_min, window_seconds=60):
                raise HTTPException(status_code=429, detail="Demasiadas solicitudes (invitado). Intenta más tarde.")
            if len(payload.content or "") > settings.chat_prompt_max_chars_guest:
                raise HTTPException(status_code=413, detail="Prompt demasiado largo para invitado")
        else:
            uid_key = f"user:{payload.user_id}:{request.client.host if request.client else ''}"
            if not rate_limit.allow((uid_key, "/chat/ask"), limit=settings.chat_auth_rate_per_min, window_seconds=60):
                raise HTTPException(status_code=429, detail="Demasiadas solicitudes. Intenta más tarde.")
            if len(payload.content or "") > settings.chat_prompt_max_chars_auth:
                raise HTTPException(status_code=413, detail="Prompt demasiado largo")
        if not conversation_id:
            if not payload.create_if_missing:
                raise HTTPException(status_code=400, detail="conversation_id requerido cuando create_if_missing=false")
            conversation_id = insert_conversation({
                "user_id": payload.user_id,
                "model": effective_model,
                "title": payload.content[:80] if payload.content else "",
                "session_id": session_id,
                "mode": mode,
            })

        # Mensaje del usuario
        user_msg_id = insert_message({
            "conversation_id": conversation_id,
            "user_id": payload.user_id,
            "role": "user",
            "content": payload.content,
            "attachments": [],
            "session_id": session_id,
        })

        # Contexto por email (si existe)
        email = str(user.get("email")) if (user and user.get("email")) else ""

        # Historial reciente para hints conversacionales (excluye el último mensaje que acabamos de insertar)
        prev_text = None
        prev_messages = []
        try:
            history = repo_list_messages(conversation_id=conversation_id)
            if history:
                prev_messages = history[:-1]
                if prev_messages:
                    prev_text = prev_messages[-1].get("content") or None
        except Exception:
            prev_text = None
            prev_messages = []

        # Obtiene entity_focus previo (memoria) de la conversación
        entity_focus = None
        try:
            conv = repo_get_conversation(conversation_id)
            if conv and conv.get("metadata"):
                entity_focus = (conv["metadata"] or {}).get("entity_focus")
        except Exception:
            entity_focus = None

        ans = ask_service.ask(
            email or "",
            payload.content,
            prev_text=prev_text,
            prev_messages=prev_messages,
            entity_focus=entity_focus,
        )
        answer_text = ans.get("respuesta") or "Sin respuesta"
        attachments_out = ans.get("attachments") or []

        # Mensaje del asistente
        asst_msg_id = insert_message({
            "conversation_id": conversation_id,
            "user_id": payload.user_id,
            "role": "assistant",
            "content": answer_text,
            "attachments": attachments_out,
            "session_id": session_id,
        })

        out = ChatAskOut(
            conversation_id=conversation_id,
            user_message=MessageOut(
                conversation_id=conversation_id,
                user_id=payload.user_id,
                role="user",
                content=payload.content,
                attachments=[],
                citations=[],
                model_snapshot=effective_model,
                tokens_input=None,
                tokens_output=None,
                error=None,
                created_at="",
            ),
            assistant_message=MessageOut(
                conversation_id=conversation_id,
                user_id=payload.user_id,
                role="assistant",
                content=answer_text,
                attachments=attachments_out,
                citations=[],
                model_snapshot=effective_model,
                tokens_input=None,
                tokens_output=None,
                error=None,
                created_at="",
            ),
            model=effective_model,
            session_id=session_id,
        ).model_dump()

        # Actualiza memoria conversacional (resumen + foco de entidad)
        try:
            from app.services.memory_service import summarize_incremental, choose_entity_focus

            prev_summary = None
            conv = repo_get_conversation(conversation_id)
            if conv:
                meta = conv.get("metadata") or {}
                prev_summary = meta.get("summary")
            new_summary = summarize_incremental(prev_summary, payload.content, answer_text)
            entity_focus = choose_entity_focus(prev_messages, payload.content, answer_text)
            fields = {"summary": new_summary}
            if entity_focus:
                fields["entity_focus"] = entity_focus
            repo_update_conv_meta_fields(conversation_id, fields)
        except Exception:
            pass

        # Guardado opcional como nota
        if payload.save_note:
            try:
                insert_note_doc({
                    "user_id": payload.user_id,
                    "title": payload.note_title or (payload.content[:80] if payload.content else "Nota de chat"),
                    "body": answer_text,
                    "tags": [str(t).strip().lower() for t in (payload.note_tags or [])],
                    "status": "active",
                    "source": "assistant",
                    "related_conversation_id": conversation_id,
                })
            except Exception:
                pass

        dt_ms = int((monotonic() - t0) * 1000)
        # Log sencillo
        _log.info("/chat/ask mode=%s model=%s latency_ms=%s", mode, effective_model, dt_ms)
        return {"message": "ok", **out, "user_message_id": user_msg_id, "assistant_message_id": asst_msg_id, "latency_ms": dt_ms}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo procesar la pregunta: {e}")


@router.post(
    "/ask/stream",
    summary="Preguntar con streaming (SSE)",
    description="Emite la respuesta del asistente en chunks (Server‑Sent Events).",
)
def chat_ask_stream(payload: ChatAskPayload, request: Request, x_session_id: Optional[str] = Header(default=None)):
    """
    Variante con SSE (Server-Sent Events). Emite el texto del asistente en `data:` por chunks.
    Al finalizar, inserta el mensaje del asistente completo y opcionalmente una nota.
    """
    try:
        t0 = monotonic()
        conversation_id = payload.conversation_id
        effective_model = payload.model or (settings.openai_model_primary if settings.openai_api_key else f"ollama:{settings.ollama_model}")
        user = None
        if payload.user_id:
            auth_header = request.headers.get("authorization")
            current = get_current_user(authorization=auth_header)
            if str(current.get("_id")) != str(payload.user_id):
                raise HTTPException(status_code=403, detail="user_id no coincide con el token")
            user = current
        mode = "auth" if user else "guest"
        session_id = payload.session_id or x_session_id
        if mode == "guest":
            if not session_id:
                import uuid
                session_id = str(uuid.uuid4())
            if not rate_limit.allow((session_id, "/chat/ask/stream"), limit=settings.chat_guest_stream_rate_per_min, window_seconds=60):
                raise HTTPException(status_code=429, detail="Demasiadas solicitudes (invitado). Intenta más tarde.")
            if len(payload.content or "") > settings.chat_prompt_max_chars_guest:
                raise HTTPException(status_code=413, detail="Prompt demasiado largo para invitado")
        else:
            uid_key = f"user:{payload.user_id}:{request.client.host if request.client else ''}"
            if not rate_limit.allow((uid_key, "/chat/ask/stream"), limit=settings.chat_auth_stream_rate_per_min, window_seconds=60):
                raise HTTPException(status_code=429, detail="Demasiadas solicitudes. Intenta más tarde.")
            if len(payload.content or "") > settings.chat_prompt_max_chars_auth:
                raise HTTPException(status_code=413, detail="Prompt demasiado largo")
        if not conversation_id:
            if not payload.create_if_missing:
                raise HTTPException(status_code=400, detail="conversation_id requerido cuando create_if_missing=false")
            conversation_id = insert_conversation({
                "user_id": payload.user_id,
                "model": effective_model,
                "title": payload.content[:80] if payload.content else "",
                "session_id": session_id,
                "mode": mode,
            })

        # Inserta mensaje del usuario
        insert_message({
            "conversation_id": conversation_id,
            "user_id": payload.user_id,
            "role": "user",
            "content": payload.content,
            "attachments": [],
            "session_id": session_id,
        })

        # Prepara respuesta completa (sin streaming real del proveedor, se chunkea localmente)
        email = None
        try:
            u = get_user_by_id(payload.user_id)
            if u and u.get("email"):
                email = str(u.get("email"))
        except Exception:
            pass

        # Historial reciente (excluye este mensaje recién insertado)
        prev_messages = []
        prev_text = None
        try:
            history = repo_list_messages(conversation_id=conversation_id)
            if history:
                prev_messages = history[:-1]
                if prev_messages:
                    prev_text = prev_messages[-1].get("content") or None
        except Exception:
            pass

        # Obtiene entity_focus previo
        entity_focus = None
        try:
            conv = repo_get_conversation(conversation_id)
            if conv and conv.get("metadata"):
                entity_focus = (conv["metadata"] or {}).get("entity_focus")
        except Exception:
            pass

        ans = ask_service.ask(email or "", payload.content, prev_text=prev_text, prev_messages=prev_messages, entity_focus=entity_focus)
        full_text = (ans.get("respuesta") or "Sin respuesta").strip()
        attachments_out = ans.get("attachments") or []

        def _gen():
            # Envia “open”
            yield "event: open\n" + "data: {}\n\n"
            # Chunks de ~120 caracteres para Postman/DevTools
            size = 120
            for i in range(0, len(full_text), size):
                chunk = full_text[i : i + size]
                yield f"data: {chunk}\n\n"
            yield "event: end\n" + "data: {}\n\n"

        # Tras crear el generador, persiste el mensaje completo del asistente (no bloquea streaming)
        try:
            insert_message({
                "conversation_id": conversation_id,
                "user_id": payload.user_id,
                "role": "assistant",
                "content": full_text,
                "attachments": attachments_out,
                "session_id": session_id,
            })
            if payload.save_note:
                try:
                    insert_note_doc({
                        "user_id": payload.user_id,
                        "title": payload.note_title or (payload.content[:80] if payload.content else "Nota de chat"),
                        "body": full_text,
                        "tags": [str(t).strip().lower() for t in (payload.note_tags or [])],
                        "status": "active",
                        "source": "assistant",
                        "related_conversation_id": conversation_id,
                    })
                except Exception:
                    pass
        except Exception:
            pass

        resp = StreamingResponse(_gen(), media_type="text/event-stream")
        dt_ms = int((monotonic() - t0) * 1000)
        _log.info("/chat/ask/stream mode=%s model=%s latency_ms=%s", mode, effective_model, dt_ms)
        return resp
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo procesar la pregunta (stream): {e}")
