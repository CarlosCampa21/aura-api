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
    update_conversation_meta as repo_update_conversation,
    get_conversation as repo_get_conversation,
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
    description="Elimina la conversación y sus mensajes (hard delete). Requiere pertenencia por user_id o session_id.",
)
def delete_conversation_route(conversation_id: str, request: Request, hard: bool = Query(True), user_id: Optional[str] = Query(default=None), x_session_id: Optional[str] = Header(default=None)):
    try:
        conv = repo_get_conversation(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Autorización: por usuario autenticado o por sesión invitado
        if user_id:
            auth_header = request.headers.get("authorization")
            current = get_current_user(authorization=auth_header)
            if str(current.get("_id")) != str(user_id) or str(conv.get("user_id") or "") != str(user_id):
                raise HTTPException(status_code=403, detail="No autorizado para eliminar esta conversación")
        else:
            # modo invitado: verifica session id
            if str(conv.get("session_id") or "") != str(x_session_id or ""):
                raise HTTPException(status_code=403, detail="No autorizado (sesión inválida)")

        if not hard:
            repo_update_conversation(conversation_id, {"status": "archived"})
            return {"message": "ok", "archived": True}

        # Hard delete con cascade messages
        n_msgs = repo_delete_msgs_by_conv(conversation_id)
        n_conv = repo_delete_conversation(conversation_id)
        return {"message": "ok", "deleted_messages": n_msgs, "deleted_conversations": n_conv}
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

        # Historial (N últimos mensajes) antes de insertar el mensaje actual
        history_msgs = []
        try:
            prev = repo_list_messages(conversation_id=conversation_id)
            if prev:
                n = max(0, int(settings.chat_history_n))
                history_msgs = prev[-n:]
        except Exception:
            history_msgs = []

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

        ans = ask_service.ask(email or "", payload.content, history=history_msgs)
        base_text = ans.get("respuesta") or "Sin respuesta"
        followup = (ans.get("followup") or "").strip()
        # Construye texto visible para UI (sin citas; opcionalmente agrega follow-up)
        answer_text = base_text
        if followup:
            answer_text += f"\n{followup}"
        attachments_out = ans.get("attachments") or []
        citations_out = []
        if ans.get("offer_code"):
            citations_out.append({"offer": ans.get("offer_code")})

        # Mensaje del asistente
        asst_msg_id = insert_message({
            "conversation_id": conversation_id,
            "user_id": payload.user_id,
            "role": "assistant",
            "content": answer_text,
            "attachments": attachments_out,
            "citations": citations_out,
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
                citations=citations_out,
                model_snapshot=effective_model,
                tokens_input=None,
                tokens_output=None,
                error=None,
                created_at="",
            ),
            model=effective_model,
            session_id=session_id,
        ).model_dump()

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
        enriched = {
            "came_from": ans.get("came_from"),
            "citation": ans.get("citation"),
            "followup": ans.get("followup"),
            "source_chunks": ans.get("source_chunks") or [],
        }
        base = {"message": "ok", **out, "user_message_id": user_msg_id, "assistant_message_id": asst_msg_id, "latency_ms": dt_ms}
        base.update(enriched)
        return base
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

        ans = ask_service.ask(email or "", payload.content)
        base_text = (ans.get("respuesta") or "Sin respuesta").strip()
        followup = (ans.get("followup") or "").strip()
        full_text = base_text
        if followup:
            full_text += f"\n{followup}"
        attachments_out = ans.get("attachments") or []

        def _gen():
            # Envia “open”
            yield "event: open\n" + "data: {}\n\n"
            if getattr(settings, "chat_stream_single_event", False):
                # Un solo evento con todo el texto
                yield f"data: {full_text}\n\n"
            else:
                # Chunks configurables (por defecto 400)
                size = max(80, int(settings.chat_stream_chunk_chars))
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
