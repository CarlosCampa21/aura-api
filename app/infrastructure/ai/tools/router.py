"""
Orquestador de tool‑calling con OpenAI.

El modelo decide si invocar herramientas como `get_schedule` (horario) o
`get_now` (hora actual). Si usa tools, ejecutamos la función real y, si hace falta,
hacemos una segunda pasada para que el asistente forme la respuesta final.
"""
from __future__ import annotations

from typing import Optional, Any, Dict, List
from openai import BadRequestError

from app.core.config import settings
from app.infrastructure.ai.openai_client import get_openai
from app.services.schedule_service import get_schedule_answer, get_schedule_payload
from app.services.library_service import search_document_answer
from app.core.time import now_text


def _parse_args(s: Optional[str]) -> Dict[str, Any]:
    """Intenta parsear argumentos JSON del tool; retorna {} en error o vacío."""
    if not s:
        return {}
    try:
        import json
        return json.loads(s)
    except Exception:
        return {}


def answer_with_tools(user_email: str, question: str, academic_context: str, history: List[Dict[str, Any]] | None = None) -> Optional[Dict[str, Any]]:
    """
    Devuelve texto final si OpenAI decide usar tool-calling o responde directamente.
    Si no hay cliente o algo falla, retorna None para que el caller haga fallback.
    """
    oa = get_openai()
    if not oa:
        return None

    sys_prompt = (
        "Eres Aura, asistente académico de la UABCS (Estilo C: institucional, cordial y profesional). "
        "Decides si usar herramientas. "
        "Primero puedes consultar la hora actual con get_now para anclarte a la fecha y zona horaria del alumno. "
        "Para preguntas de horarios (qué clase me toca, qué materias tengo hoy, lunes, mañana, ahorita), usa get_schedule. "
        "Si falta especificar el día/momento, pide una aclaración breve y luego usa el tool correspondiente. "
        "Responde en español, claro y conciso (1–2 oraciones). Si no hay información suficiente, dilo."
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_schedule",
                "description": "Consulta el horario del alumno y devuelve las clases para un momento indicado.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "when": {
                            "type": "string",
                            "enum": ["now", "today", "tomorrow", "day"],
                            "description": "Momento a consultar: ahora, hoy, mañana o un día específico",
                        },
                        "day_name": {
                            "type": "string",
                            "description": "Nombre del día en español cuando when='day' (lunes..sábado)",
                        },
                    },
                    "required": ["when"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_now",
                "description": "Obtiene la fecha y hora actuales en la zona horaria del alumno.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tz": {"type": "string", "description": "Zona horaria IANA opcional; si falta, se usa la del perfil"}
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_document",
                "description": "Busca un documento institucional (ej. formatos, PDFs) y devuelve el mejor match con enlace",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Descripción del documento a buscar (ej. carta presentación prácticas)"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
    ]

    # Mapea historial simple (user/assistant) a mensajes previos
    history_msgs: List[Dict[str, Any]] = []
    try:
        for m in (history or [])[-20:]:
            r = str(m.get("role") or "").lower()
            if r in {"user", "assistant"}:
                c = str(m.get("content") or "").strip()
                if c:
                    history_msgs.append({"role": r, "content": c})
    except Exception:
        history_msgs = []

    messages: List[Dict[str, Any]] = (
        [{"role": "system", "content": sys_prompt},
         {"role": "system", "content": f"Contexto académico breve:\n{academic_context}"}]
        + history_msgs
        + [{"role": "user", "content": question}]
    )

    def call(model: str, msgs):
        return oa.chat.completions.create(
            model=model,
            messages=msgs,
            tools=tools,
            tool_choice="auto",
            temperature=settings.chat_temperature,
            top_p=settings.chat_top_p,
            presence_penalty=settings.chat_presence_penalty,
            frequency_penalty=settings.chat_frequency_penalty,
        )

    try:
        first = call(settings.openai_model_primary, messages)
    except BadRequestError:
        first = call(settings.openai_model_fallback, messages)
    except Exception:
        return None

    msg = first.choices[0].message
    # Si el modelo decidió responder directamente
    if not getattr(msg, "tool_calls", None):
        return {"answer": (msg.content or "").strip() or "", "origin": "assistant"}

    # Ejecuta tool(s) solicitados. Para `get_schedule` podemos devolver
    # la respuesta directa. Si sólo se invoca `get_now`, hacemos una
    # segunda pasada para permitir una acción posterior.
    tool_messages: List[Dict[str, Any]] = []
    called_schedule = False
    called_document = False
    # Guardar payloads estructurados cuando aplique
    schedule_payload: Dict[str, Any] | None = None
    for tc in msg.tool_calls or []:
        if tc.type != "function":
            continue
        if tc.function and tc.function.name == "get_schedule":
            args = _parse_args(getattr(tc.function, "arguments", None))
            when = str(args.get("when") or "").lower()
            day_name = args.get("day_name")
            # Devolver payload estructurado
            payload = get_schedule_payload(user_email, when, day_name)
            schedule_payload = payload
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": "get_schedule",
                "content": __import__("json").dumps(payload),
            })
            called_schedule = True
        elif tc.function and tc.function.name == "get_now":
            args = _parse_args(getattr(tc.function, "arguments", None))
            tz = args.get("tz")
            tool_result = now_text(user_email, tz)
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": "get_now",
                "content": tool_result,
            })
        elif tc.function and tc.function.name == "get_document":
            args = _parse_args(getattr(tc.function, "arguments", None))
            q = str(args.get("query") or "")
            tool_result = search_document_answer(q) or "No encontré un documento con esa descripción."
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": "get_document",
                "content": tool_result,
            })
            called_document = True
    # Siempre hacer segunda pasada para que el modelo redacte la respuesta final
    if tool_messages:
        try:
            second = call(settings.openai_model_primary, messages + [{"role": "assistant", "content": msg.content or "", "tool_calls": msg.tool_calls}] + tool_messages)
        except BadRequestError:
            second = call(settings.openai_model_fallback, messages + [{"role": "assistant", "content": msg.content or "", "tool_calls": msg.tool_calls}] + tool_messages)
        except Exception:
            # Regresa contenido del último tool como fallback (texto)
            return {"answer": tool_messages[-1]["content"], "origin": "tool"}

        msg2 = second.choices[0].message
        out_text = (msg2.content or "").strip() or tool_messages[-1]["content"]
        origin = "tool:get_schedule" if called_schedule else ("tool:get_document" if called_document else "tool")
        return {"answer": out_text, "origin": origin, "schedule": schedule_payload}

    # Sin tools: respuesta directa
    return {"answer": (msg.content or "").strip() or "", "origin": "assistant"}
