# app/services/ai_service.py
from openai import BadRequestError
from app.core.config import settings
from app.infrastructure.ai.openai_client import get_openai
from app.infrastructure.ai.ollama_client import ollama_ask

SYSTEM_PROMPT = (
    "Eres Aura, una IA que apoya a alumnos de la UABCS. "
    "Responde breve, clara y con pasos accionables cuando aplique. "
    "Si faltan datos, dilo y sugiere qué falta."
)

def ask_llm(question: str, context: str = "") -> str:
    """
    Estrategia:
      1) OpenAI (modelo primario)
      2) OpenAI (fallback)
      3) Ollama local (si no hay API key o si OpenAI falla)
    """
    user_prompt = f"Contexto:\n{context}\n---\nPregunta: {question}"
    oa = get_openai()

    # 1) y 2) → OpenAI si hay API key
    if oa:
        try:
            resp = oa.chat.completions.create(
                model=settings.openai_model_primary,
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": user_prompt}],
                temperature=0.2,
            )
            out = (resp.choices[0].message.content or "").strip()
            return out or "Sin respuesta."
        except BadRequestError:
            # Fallback de modelo
            try:
                resp = oa.chat.completions.create(
                    model=settings.openai_model_fallback,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT},
                              {"role": "user", "content": user_prompt}],
                    temperature=0.2,
                )
                out = (resp.choices[0].message.content or "").strip()
                return out or "Sin respuesta."
            except Exception:
                pass
        except Exception:
            pass

    # 3) → Ollama (sin key o error en OpenAI)
    try:
        return ollama_ask(SYSTEM_PROMPT, user_prompt, temperature=0.2, timeout=30) or "Sin respuesta."
    except Exception:
        return "Aura (local): no pude consultar el modelo."
