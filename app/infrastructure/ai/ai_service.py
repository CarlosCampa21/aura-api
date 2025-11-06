"""Cliente LLM de alto nivel (OpenAI → fallback → Ollama)."""
from openai import BadRequestError
import logging
from app.core.config import settings
from app.infrastructure.ai.openai_client import get_openai
from app.infrastructure.ai.ollama_client import ollama_ask

SYSTEM_PROMPT = (
    "Eres AURA, asistente institucional de la Universidad Autónoma de Baja California Sur. "
    "Habla en español, claro y cordial, y usa el historial para mantener continuidad. "
    "No incluyas citas, referencias entre paréntesis ni nombres de fuentes al final. "
    "Si en el turno previo ofreciste una acción (p. ej., '¿Quieres ver fechas de exámenes?') y el usuario responde afirmativamente (sí/ok/claro), "
    "ejecuta la acción y entrega el contenido directamente (sin frases vacías). "
    "No inventes datos; si falta información, dilo brevemente y sugiere una opción concreta para continuar."
)


def ask_llm(
    question: str,
    context: str = "",
    history: list[dict] | None = None,
    *,
    system: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    presence_penalty: float | None = None,
    frequency_penalty: float | None = None,
    max_tokens: int | None = None,
) -> str:
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
    sys_prompt = system or SYSTEM_PROMPT
    temp = settings.chat_temperature if temperature is None else float(temperature)
    tp = settings.chat_top_p if top_p is None else float(top_p)
    pres = settings.chat_presence_penalty if presence_penalty is None else float(presence_penalty)
    freq = settings.chat_frequency_penalty if frequency_penalty is None else float(frequency_penalty)

    if oa:
        try:
            resp = oa.chat.completions.create(
                model=settings.openai_model_primary,
                messages=(
                    [{"role": "system", "content": sys_prompt}] + history_msgs + [
                        {"role": "user", "content": user_prompt}
                    ]
                ),
                temperature=temp,
                top_p=tp,
                presence_penalty=pres,
                frequency_penalty=freq,
                max_tokens=max_tokens,
            )
            out = (resp.choices[0].message.content or "").strip()
            return out or "Sin respuesta."
        except BadRequestError:
            # Fallback de modelo
            try:
                resp = oa.chat.completions.create(
                    model=settings.openai_model_fallback,
                    messages=(
                        [{"role": "system", "content": sys_prompt}] + history_msgs + [
                            {"role": "user", "content": user_prompt}
                        ]
                    ),
                    temperature=temp,
                    top_p=tp,
                    presence_penalty=pres,
                    frequency_penalty=freq,
                    max_tokens=max_tokens,
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
                sys_prompt,
                user_prompt,
                temperature=temp,
                timeout=settings.ollama_timeout_seconds,
            )
            or "Sin respuesta."
        )
    except Exception as e:
        logging.getLogger("aura.ai").exception("Fallo en Ollama fallback: %s", e)
        return "Aura (local): no pude consultar el modelo."
