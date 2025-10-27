"""
Orquestador de tool-calling con OpenAI.

El modelo decide si invocar el tool `get_schedule` para responder
preguntas como "qué clase me toca". Si llama el tool, ejecutamos
la función real y hacemos una segunda llamada al modelo para que
forme la respuesta final al usuario.
"""
from __future__ import annotations

from typing import Optional, Any, Dict, List
from openai import BadRequestError

from app.core.config import settings
from app.infrastructure.ai.openai_client import get_openai
from app.services.schedule_service import get_schedule_answer
from app.services.time_service import now_text


def answer_with_tools(user_email: str, question: str, academic_context: str) -> Optional[str]:
    """
    Devuelve texto final si OpenAI decide usar tool-calling o responde directamente.
    Si no hay cliente o algo falla, retorna None para que el caller haga fallback.
    """
    oa = get_openai()
    if not oa:
        return None

    sys = (
        "Eres Aura, asistente académico de la UABCS. "
        "Decides si usar herramientas. "
        "Primero puedes consultar la hora actual con get_now para anclarte a la fecha y zona horaria del alumno. "
        "Para preguntas de horarios (qué clase me toca, qué materias tengo hoy, lunes, mañana, ahorita), usa get_schedule. "
        "Si falta especificar el día/momento, pide una aclaración breve y luego usa el tool correspondiente. "
        "Responde en español, breve y accionable."
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
        }
    ]

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": sys},
        {"role": "system", "content": f"Contexto académico breve:\n{academic_context}"},
        {"role": "user", "content": question},
    ]

    def call(model: str, msgs):
        return oa.chat.completions.create(
            model=model,
            messages=msgs,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
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
        return (msg.content or "").strip() or None

    # Ejecuta tool(s) solicitados. Para `get_schedule` podemos devolver
    # la respuesta directa. Si sólo se invoca `get_now`, hacemos una
    # segunda pasada para permitir una acción posterior.
    tool_messages: List[Dict[str, Any]] = []
    called_schedule = False
    for tc in msg.tool_calls or []:
        if tc.type != "function":
            continue
        if tc.function and tc.function.name == "get_schedule":
            import json
            args = {}
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            when = str(args.get("when") or "").lower()
            day_name = args.get("day_name")
            tool_result = get_schedule_answer(user_email, when, day_name)
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": "get_schedule",
                "content": tool_result,
            })
            called_schedule = True
        elif tc.function and tc.function.name == "get_now":
            import json
            args = {}
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            tz = args.get("tz")
            tool_result = now_text(user_email, tz)
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": "get_now",
                "content": tool_result,
            })
    # Si ya obtuvimos horario, respondemos con él directamente
    if called_schedule and tool_messages:
        return next((m["content"] for m in reversed(tool_messages) if m.get("name") == "get_schedule"), tool_messages[-1]["content"])

    # Si sólo hubo get_now (o ningún tool), hacemos una segunda pasada
    if tool_messages:
        try:
            second = call(settings.openai_model_primary, messages + [{"role": "assistant", "content": msg.content or "", "tool_calls": msg.tool_calls}] + tool_messages)
        except BadRequestError:
            second = call(settings.openai_model_fallback, messages + [{"role": "assistant", "content": msg.content or "", "tool_calls": msg.tool_calls}] + tool_messages)
        except Exception:
            # Regresa contenido del último tool como fallback
            return tool_messages[-1]["content"]

        msg2 = second.choices[0].message
        # Si en la segunda pasada llama get_schedule, ejecútalo y devuelve su contenido
        if getattr(msg2, "tool_calls", None):
            for tc in msg2.tool_calls or []:
                if tc.type == "function" and tc.function and tc.function.name == "get_schedule":
                    import json
                    args = {}
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        args = {}
                    when = str(args.get("when") or "").lower()
                    day_name = args.get("day_name")
                    return get_schedule_answer(user_email, when, day_name)
        return (msg2.content or "").strip() or tool_messages[-1]["content"]

    # Sin tools: respuesta directa
    return (msg.content or "").strip() or None
