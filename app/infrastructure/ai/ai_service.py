"""Cliente LLM de alto nivel (OpenAI → fallback → Ollama)."""
from openai import BadRequestError
import logging
from app.core.config import settings
from app.infrastructure.ai.openai_client import get_openai
from app.infrastructure.ai.ollama_client import ollama_ask

SYSTEM_PROMPT = (
    "Eres AURA, asistente institucional de la Universidad Autónoma de Baja California Sur. "
    "Habla en español con un tono claro, profesional y cordial. "
    "Usa el historial para mantener continuidad en la conversación. "
    "Responde con la información solicitada de forma precisa. "
    "Si aplica, ofrece un apoyo adicional relacionado (por ejemplo: si preguntan una fecha, ofrecer ver el PDF oficial o información relacionada). "
    "No inventes datos fuera del conocimiento entregado por el modelo o herramientas internas. "
    "Si no tienes información suficiente, dilo amablemente y ofrece opciones para continuar."
)



def ask_llm(question: str, context: str = "", history: list[dict] | None = None) -> str:
    """
    Estrategia:
      1) OpenAI (modelo primario)
      2) OpenAI (fallback)
      3) Ollama local (si no hay API key o si OpenAI falla)
    """
    user_prompt = f"Contexto:\n{context}\n---\nPregunta: {question}"
    # Mapea historial simple (user/assistant) a mensajes previos
    history_msgs = []
    try:
        for m in (history or [])[-20:]:  # límite defensivo
            r = str(m.get("role") or "").lower()
            if r in {"user", "assistant"}:
                c = str(m.get("content") or "").strip()
                if c:
                    history_msgs.append({"role": r, "content": c})
    except Exception:
        history_msgs = []
    oa = get_openai()

    if oa:
        try:
            resp = oa.chat.completions.create(
                model=settings.openai_model_primary,
                messages=(
                    [{"role": "system", "content": SYSTEM_PROMPT}] + history_msgs + [
                        {"role": "user", "content": user_prompt}
                    ]
                ),
                temperature=settings.chat_temperature,
                top_p=settings.chat_top_p,
                presence_penalty=settings.chat_presence_penalty,
                frequency_penalty=settings.chat_frequency_penalty,
            )
            out = (resp.choices[0].message.content or "").strip()
            return out or "Sin respuesta."
        except BadRequestError:
            # Fallback de modelo
            try:
                resp = oa.chat.completions.create(
                    model=settings.openai_model_fallback,
                    messages=(
                        [{"role": "system", "content": SYSTEM_PROMPT}] + history_msgs + [
                            {"role": "user", "content": user_prompt}
                        ]
                    ),
                    temperature=settings.chat_temperature,
                    top_p=settings.chat_top_p,
                    presence_penalty=settings.chat_presence_penalty,
                    frequency_penalty=settings.chat_frequency_penalty,
                )
                out = (resp.choices[0].message.content or "").strip()
                return out or "Sin respuesta."
            except Exception:
                pass
        except Exception:
            pass

    # 3) → Ollama (sin key o error en OpenAI)
    try:
        return (
            ollama_ask(
                SYSTEM_PROMPT,
                user_prompt,
                temperature=0.2,
                timeout=settings.ollama_timeout_seconds,
            )
            or "Sin respuesta."
        )
    except Exception as e:
        logging.getLogger("aura.ai").exception("Fallo en Ollama fallback: %s", e)
        return "Aura (local): no pude consultar el modelo."
