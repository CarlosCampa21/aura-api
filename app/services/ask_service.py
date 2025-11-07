"""Orquestación de preguntas del usuario hacia el asistente (IA + tools)."""
import random
from app.infrastructure.ai.ai_service import ask_llm
from app.services.context_service import build_academic_context
from app.services.schedule_service import try_answer_schedule
from app.infrastructure.ai.tools.router import answer_with_tools
import re
from app.services.rag_search_service import answer_with_rag
from datetime import datetime
from zoneinfo import ZoneInfo
from app.core.time import get_user_tz
from app.core.config import settings


def ask(user_email: str, question: str, history: list[dict] | None = None) -> dict:
    """Construye contexto y responde usando tool‑calling u LLM.

    Flujo:
    1) Construye contexto académico breve
    2) Intenta tool‑calling (get_schedule/get_now)
    3) Fallback local de horario
    4) Fallback LLM (OpenAI→Ollama)
    """
    # 0) Confirmación sí/no de una oferta del turno anterior
    if _is_yes_or_no(question):
        offer = _last_offer(history)
        if offer:
            if _is_yes(question):
                if offer == "offer_exam_dates":
                    try:
                        rag = answer_with_rag("Fechas de exámenes ordinarios del semestre actual UABCS", k=10)
                        ans = str(rag.get("answer") or "Aquí tienes las fechas clave.")
                        return {
                            "pregunta": question,
                            "respuesta": ans,
                            "contexto_usado": True,
                            "came_from": "rag-followup",
                            "citation": "",
                            "source_chunks": [],
                            "followup": "",
                            "attachments": _extract_urls(ans),
                        }
                    except Exception:
                        return {
                            "pregunta": question,
                            "respuesta": "Aquí tienes las fechas clave del calendario.",
                            "contexto_usado": False,
                            "came_from": "followup",
                            "citation": "",
                            "source_chunks": [],
                            "followup": "",
                            "attachments": [],
                        }
                if offer == "offer_open_pdf":
                    try:
                        from app.services.library_service import find_calendar_pdf_url
                        hit = find_calendar_pdf_url()
                    except Exception:
                        hit = None
                    if hit and hit.get("url"):
                        url = str(hit.get("url"))
                        title = str(hit.get("title") or "Calendario escolar")
                        text = f"Aquí está el PDF del calendario: {url}"
                        return {
                            "pregunta": question,
                            "respuesta": text,
                            "contexto_usado": True,
                            "came_from": "asset",
                            "citation": "",
                            "source_chunks": [],
                            "followup": "",
                            "attachments": [url],
                        }
                    # Fallback si no se encuentra en assets
                    return {
                        "pregunta": question,
                        "respuesta": "No encontré el PDF en la biblioteca en este momento.",
                        "contexto_usado": False,
                        "came_from": "asset-miss",
                        "citation": "",
                        "source_chunks": [],
                        "followup": "¿Quieres que lo busque por otro nombre?",
                        "attachments": [],
                    }
                if offer == "offer_set_reminder":
                    return {
                        "pregunta": question,
                        "respuesta": "Hecho. Te recordaré tus próximas clases.",
                        "contexto_usado": False,
                        "came_from": "followup-local",
                        "citation": "",
                        "source_chunks": [],
                        "followup": "",
                        "attachments": [],
                    }
            # Negación explícita
            return {
                "pregunta": question,
                "respuesta": "Entendido.",
                "contexto_usado": False,
                "came_from": "followup-decline",
                "citation": "",
                "source_chunks": [],
                "followup": "",
                "attachments": [],
            }

    # A) Intención social (saludo/agradecimiento/despedida): no activar RAG ni tools
    intent = _detect_social_intent(question)
    if intent:
        text = _social_llm_reply(question, history)
        return {
            "pregunta": question,
            "respuesta": text,
            "contexto_usado": False,
            "came_from": "chat-social",
            "citation": "",
            "source_chunks": [],
            "followup": "",
            "attachments": [],
        }

    # B) Si no parece intención académica, conversar sin RAG (permite variación y contexto)
    if not _is_academic_intent(question):
        answer = _social_llm_reply(question, history)
        return {
            "pregunta": question,
            "respuesta": answer,
            "contexto_usado": False,
            "came_from": "chat-free",
            "citation": "",
            "source_chunks": [],
            "followup": "",
            "attachments": [],
        }

    # C) Intención académica → casos directos (calendario)
    if _is_calendar_request(question):
        return _answer_calendar_request(question, history)

    # C1.5) Desambiguación: nombre suelto sin apellidos → pedir más contexto
    disamb = _maybe_disambiguate_person(question)
    if disamb:
        return {
            "pregunta": question,
            "respuesta": disamb,
            "contexto_usado": False,
            "came_from": "clarify",
            "citation": "",
            "source_chunks": [],
            "followup": "",
            "attachments": [],
        }

    # C2) Construye contexto breve
    ctx = build_academic_context(user_email)

    # 2) RAG primero: si hay evidencia útil, nos quedamos con esa respuesta
    try:
        q_eff = _rewrite_temporal_phrases(question, user_email)
        q_eff = _bias_asueto_query(q_eff)
        q_eff = _bias_exam_query(q_eff)
        q_eff = _bias_upcoming_query(q_eff, user_email)
        # Si el turno anterior fue de contacto/correo y el usuario dice
        # "ahora el de <nombre>", infiere que sigue pidiendo correos
        q_eff = _infer_followup_attribute(q_eff, history)
        q_eff = _bias_people_query(q_eff, history)
        # Si el usuario usa pronombres ("su correo"), agrega la última persona del historial
        q_eff = _augment_query_with_last_person(q_eff, history)
        rag = answer_with_rag(q_eff, k=30, continuation_person=_last_person_from_history(history))
        if rag and rag.get("used_context") and rag.get("answer"):
            ans = _clean_text(str(rag.get("answer") or ""))
            ans = _strip_irrelevant_contact(ans, question)
            return {
                "pregunta": question,
                "respuesta": ans,
                "contexto_usado": True,
                "came_from": rag.get("came_from") or "rag",
                "citation": rag.get("citation") or "",
                "source_chunks": rag.get("source_chunks") or [],
                "followup": ("¿Puedo ayudarte con otra cosa?") if settings.chat_followups_enabled else "",
                "offer_code": _offer_code_for(question, ans, _detect_topic(question, ans)),
                "attachments": _extract_urls(ans),
            }
    except Exception:
        pass

    # 2b) Si no hubo contexto del RAG, dejamos que el modelo decida tool/respuesta
    oa_answer = answer_with_tools(user_email, question, ctx, history=history)
    if oa_answer and isinstance(oa_answer, dict) and (oa_answer.get("answer") or "").strip():
        return {
            "pregunta": question,
            "respuesta": _strip_irrelevant_contact(_clean_text(oa_answer.get("answer") or ""), question),
            "contexto_usado": True,
            "came_from": oa_answer.get("origin") or "tool",
            "citation": "",
            "source_chunks": [],
            "followup": ("¿Puedo ayudarte con otra cosa?") if settings.chat_followups_enabled else "",
            "offer_code": _offer_code_for(question, oa_answer.get("answer") or "", _detect_topic(question, oa_answer.get("answer") or "")),
            "attachments": _extract_urls(str(oa_answer.get("answer") or "")),
        }

    # 3) Fallback local: detector simple de horario
    tool_answer = try_answer_schedule(user_email, question)
    if tool_answer:
        return {
            "pregunta": question,
            "respuesta": _strip_irrelevant_contact(_clean_text(tool_answer), question),
            "contexto_usado": True,
            "came_from": "schedule",
            "citation": "",
            "source_chunks": [],
            "followup": ("¿Puedo ayudarte con otra cosa?") if settings.chat_followups_enabled else "",
            "offer_code": _offer_code_for(question, tool_answer, _detect_topic(question, tool_answer)),
            "attachments": _extract_urls(tool_answer),
        }

    # 4) Último recurso: pipeline LLM clásico (OpenAI→Ollama)
    answer = ask_llm(question, ctx, history=history)
    answer = _strip_irrelevant_contact(answer, question)
    return {
        "pregunta": question,
        "respuesta": _clean_text(answer),
        "contexto_usado": bool(ctx and ctx != "Sin datos académicos del alumno aún."),
        "came_from": "llm",
        "citation": "",
        "source_chunks": [],
        "followup": ("¿Puedo ayudarte con otra cosa?") if settings.chat_followups_enabled else "",
        "offer_code": _offer_code_for(question, answer, _detect_topic(question, answer)),
        "attachments": _extract_urls(answer),
    }


_URL_RE = re.compile(r"https?://[^\s>]+", re.IGNORECASE)


def _extract_urls(text: str) -> list[str]:
    """Extrae URLs del texto para adjuntarlas en el mensaje.

    Filtra si hay una base pública de R2 configurada; en caso contrario, devuelve todas las URLs detectadas.
    """
    if not text:
        return []
    urls = _URL_RE.findall(text)
    try:
        from app.infrastructure.storage.r2 import public_base_url

        base = public_base_url() or ""
        if base:
            urls = [u for u in urls if u.startswith(base)]
    except Exception:
        pass
    # Dedup conservando orden
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


_SOCIAL_GREET = [
    "¡Hola! ¿En qué puedo ayudarte hoy?",
    "Hola, ¿qué necesitas?",
    "¡Hola! Aquí estoy para ayudarte.",
    "Hola, dime qué necesitas y lo vemos.",
]
_SOCIAL_THANKS = [
    "¡Con gusto! Si necesitas algo más, dime.",
    "¡De nada! ¿Algo más en lo que te ayude?",
    "Listo. ¿Te apoyo con otra cosa?",
]
_SOCIAL_BYE = [
    "¡Hasta luego! Aquí estaré si me necesitas.",
    "Nos vemos. Cuando gustes retomamos.",
    "Que estés bien. Vuelvo a ayudarte cuando quieras.",
]

_GREET_RE = re.compile(r"\b(hola|holaa|ola|buen[oa]s|qué tal|que tal|hola aura|hello|hi|hey|buen dia|buen día|buenas tardes|buenas noches)\b", re.IGNORECASE)
_THANKS_RE = re.compile(r"\b(gracias|mil gracias|muchas gracias|te agradezco|thanks|thank you)\b", re.IGNORECASE)
_BYE_RE = re.compile(r"\b(ad[ií]os|nos vemos|hasta luego|hasta pronto|bye|me despido)\b", re.IGNORECASE)

# Palabras que indican intención académica
_ACAD_HINTS = re.compile(
    r"(calendario|clases|horari|materia|inscripci|reinscripci|extraordinari|ordinari|"
    r"ex[aá]men|beca|titulaci|convocatoria|semestre|aula|sal[oó]n|docente|profesor|profesora|profe|maestro|"
    r"correo|email|e-?mail|contacto|especiali|área|area|investigaci|perfil|hoy|ma[nñ]ana|fecha|"
    r"cu[aá]ndo|d[oó]nde|c[oó]mo|pdf|asueto|asuetos|feriad|feriados|festiv|festivos|vacacion|vacacional|descanso|"
    r"no\s+hay\s+clases|sin\s+clases)",
    re.IGNORECASE,
)


def _detect_social_intent(q: str | None) -> str | None:
    s = (q or "").strip().lower()
    if not s:
        return None
    if _GREET_RE.search(s):
        return "greet"
    if _THANKS_RE.search(s):
        return "thanks"
    if _BYE_RE.search(s):
        return "bye"
    return None


def _social_reply(kind: str, history: list[dict] | None) -> str:
    last_assistant = ""
    try:
        if history:
            for m in reversed(history):
                if str(m.get("role")).lower() == "assistant":
                    last_assistant = (m.get("content") or "").lower()
                    break
    except Exception:
        last_assistant = ""
    if kind == "greet":
        if last_assistant and ("¿en qué puedo ayudarte" in last_assistant or "aquí estoy para ayudarte" in last_assistant):
            return "¿Te ayudo con calendario, materias o trámites?"
        return random.choice(_SOCIAL_GREET)
    if kind == "thanks":
        return random.choice(_SOCIAL_THANKS)
    if kind == "bye":
        return random.choice(_SOCIAL_BYE)
    return "¿En qué puedo ayudarte?"


def _is_academic_intent(q: str | None) -> bool:
    if not q:
        return False
    if _ACAD_HINTS.search(q):
        return True
    # Considera nombres como intención académica (consulta de perfil)
    return _looks_like_person_name(q)


SOCIAL_SYSTEM = (
    "Eres AURA, asistente de la UABCS. Responde saludos y charla casual en español "
    "de forma breve, cordial y profesional (1–2 oraciones). Evita conversación personal "
    "(no preguntes planes del día, estados de ánimo, etc.). Si es posible, orienta a ayuda "
    "académica de forma natural. No sugieras consultar sitios web externos; si falta información, "
    "pide un dato breve para continuar o indica que puedes buscarlo."
)


def _social_llm_reply(prompt: str, history: list[dict] | None) -> str:
    try:
        out = (
            ask_llm(
                prompt,
                context="",
                history=history or [],
                system=SOCIAL_SYSTEM,
                temperature=0.6,
                max_tokens=64,
            ).strip()
            or "Hola, ¿qué necesitas?"
        )
        # Garantiza cierre orientado a ayuda académica y evita desvíos personales
        help_re = re.compile(r"(en que puedo (ayudarte|apoyarte)|como puedo ayudarte)", re.IGNORECASE)
        personal_re = re.compile(r"\b(plan(es)?|\btu d[ií]a\b|como te sientes|que tal tu d[ií]a)\b", re.IGNORECASE)
        if settings.chat_followups_enabled and not help_re.search(out):
            # Añade una pregunta genérica de ayuda sólo si está habilitado
            out = (out.rstrip(" .!") + ". ¿Puedo ayudarte con otra cosa?").strip()
        if personal_re.search(out):
            # Sustituye partes personales por orientación útil
            out = ("¿Puedo ayudarte con otra cosa?" if settings.chat_followups_enabled else "Puedo ayudarte con tus trámites o calendario.")
        return out
    except Exception:
        # Fallback a plantillas si falla la API
        pool = _SOCIAL_GREET
        try:
            import random as _rnd
            return (_rnd.choice(pool) + " ¿En qué puedo apoyarte con calendario, materias o trámites?").strip()
        except Exception:
            return (pool[0] + " ¿En qué puedo apoyarte con calendario, materias o trámites?").strip()


def _suggest_followup_tool(question: str, origin: str | None) -> str:
    q = (question or "").lower()
    if origin and origin.startswith("tool:get_schedule"):
        return "¿Quieres que te recuerde tus próximas clases?"
    if "pdf" in q or (origin and origin.startswith("tool:get_document")):
        return "¿Te comparto el PDF oficial?"
    if "calendario" in q or "semestre" in q:
        return "¿Quieres ver también las fechas de exámenes?"
    return "¿Deseas que amplíe con información relacionada?"


# --- Respuesta directa para "calendario" (PDF + resumen) ---
_CALENDAR_REQ_RE = re.compile(r"\b(calendario|calendario\s+escolar|calendario\s+acad[eé]mico)\b", re.IGNORECASE)
_WANTS_PDF_RE = re.compile(r"\b(pdf|archivo|documento|descargar|desc[aá]rgalo|ver|abre|enlace|link)\b", re.IGNORECASE)


def _is_calendar_request(q: str | None) -> bool:
    return bool(q and _CALENDAR_REQ_RE.search(q))


def _answer_calendar_request(question: str, history: list[dict] | None = None) -> dict:
    url = None
    title = "Calendario escolar"
    try:
        from app.services.library_service import find_calendar_pdf_url

        hit = find_calendar_pdf_url()
        if hit and hit.get("url"):
            url = str(hit.get("url"))
            title = str(hit.get("title") or title)
    except Exception:
        url = None

    wants_pdf = bool(_WANTS_PDF_RE.search(question or ""))

    # Si el usuario pidió explícitamente el PDF/documento, responde minimalista
    if wants_pdf and url:
        text = f"Aquí está el documento solicitado: {url}"
        return {
            "pregunta": question,
            "respuesta": text,
            "contexto_usado": True,
            "came_from": "calendar",
            "citation": "",
            "source_chunks": [],
            "followup": "",
            "attachments": [url],
        }

    # Si no lo pidió explícitamente, ofrece PDF + resumen breve
    try:
        q = (
            "Resumen breve del calendario escolar 2025: inicio y fin de clases de ambos semestres, "
            "fechas de exámenes ordinarios y extraordinarios. En 3–5 líneas, claro y sin citas."
        )
        rag = answer_with_rag(q, k=30)
        summary = _clean_text(str(rag.get("answer") or ""))
    except Exception:
        summary = ""

    parts = []
    if url:
        parts.append(f"{title} (PDF): {url}")
    if summary:
        parts.append(summary)
    text = "\n\n".join(parts) if parts else "Aquí tienes el calendario escolar."

    return {
        "pregunta": question,
        "respuesta": text,
        "contexto_usado": True,
        "came_from": "calendar",
        "citation": "",
        "source_chunks": [],
        "followup": "",  # sin orquestación/preguntas finales
        "attachments": [url] if url else [],
    }


# --- Follow‑ups contextuales y variados ---

_TOPIC_PATTERNS = {
    "asueto": re.compile(r"\b(asueto|feriad|festiv|no\s+hay\s+clases|sin\s+clases)\b", re.IGNORECASE),
    "inicio": re.compile(r"\b(inicio\s+de\s+clases|inicia(n)?\s+clases)\b", re.IGNORECASE),
    "fin": re.compile(r"\b(fin\s+de\s+clases|termina(n)?\s+las\s+clases|fin\s+del\s+semestre)\b", re.IGNORECASE),
    "examenes": re.compile(r"ex[aá]men|ordinari|extraordinari", re.IGNORECASE),
    "inscripciones": re.compile(r"inscripci|reinscripci", re.IGNORECASE),
    "vacaciones": re.compile(r"vacacion|vacacional", re.IGNORECASE),
    "evaluacion": re.compile(r"evaluaci[oó]n\s+docente", re.IGNORECASE),
    "calendario": re.compile(r"calendario|pdf", re.IGNORECASE),
    "contacto": re.compile(r"\b(correo|email|e-?mail|mail)\b|@[a-z0-9_.-]+", re.IGNORECASE),
}

_FOLLOWUP_TEMPLATES = {
    "asueto": [
        "¿Quieres que te liste los asuetos del próximo mes?",
        "¿Deseas que verifiquemos si coinciden con fin o reinicio de clases?",
        "¿Te muestro también los asuetos del resto del semestre?",
    ],
    "inicio": [
        "¿Quieres ver inscripciones/reinscripciones cercanas a esa fecha?",
        "¿Deseas que te recuerde el primer día de clases?",
        "¿Te comparto también el periodo de reinscripciones?",
    ],
    "fin": [
        "¿Quieres que te comparta las fechas de exámenes ordinarios?",
        "¿Deseas ver qué sigue después (extraordinarios o periodo vacacional)?",
        "¿Te recuerdo el último día de clases unos días antes?",
    ],
    "examenes": [
        "¿Quieres ver extraordinarios e intersemestrales?",
        "¿Deseas agregar estas fechas a tu agenda?",
        "¿Te muestro el rango completo de evaluaciones?",
    ],
    "inscripciones": [
        "¿Quieres ver requisitos o fechas por programa?",
        "¿Deseas que te avise unos días antes?",
        "¿Te comparto el enlace para trámites?",
    ],
    "vacaciones": [
        "¿Quieres confirmar el periodo exacto de regreso a clases?",
        "¿Deseas ver si hay exámenes alrededor de esas fechas?",
        "¿Te muestro los asuetos cercanos a ese periodo?",
    ],
    "evaluacion": [
        "¿Quieres ver cómo afecta al calendario de clases?",
        "¿Deseas conocer el periodo de exámenes cercano?",
        "¿Te comparto recordatorios para completar la evaluación?",
    ],
    "calendario": [
        "¿Quieres abrir el PDF oficial del calendario?",
        "¿Deseas ver el calendario completo por secciones?",
        "¿Te comparto un resumen descargable?",
    ],
}


def _detect_topic(question: str, answer: str) -> str | None:
    text = f"{question}\n{answer}"
    for topic, rx in _TOPIC_PATTERNS.items():
        if rx.search(text):
            return topic
    return None


def _last_was_followup(history: list[dict] | None) -> bool:
    try:
        if not history:
            return False
        last = next((m for m in reversed(history) if str(m.get("role")).lower() == "assistant"), None)
        if not last:
            return False
        content = (last.get("content") or "").strip().lower()
        return content.endswith("?") and ("¿" in content)
    except Exception:
        return False


def _maybe_contextual_followup(question: str, answer: str, history: list[dict] | None) -> str:
    if not settings.chat_followups_enabled:
        return ""
    # Evita repetir si el último turno ya terminó con pregunta
    if _last_was_followup(history):
        return ""
    topic = _detect_topic(question or "", answer or "")
    if not topic:
        return ""
    # Probabilidad de ofrecer follow-up solo si hay tema claro
    import random as _rnd
    if _rnd.random() < 0.35:  # 65% de probabilidad de ofrecerlo
        return ""
    pool = _FOLLOWUP_TEMPLATES.get(topic) or []
    if not pool:
        return ""
    # Evita ofrecer lo mismo que ya se ofreció en el turno anterior (heurístico)
    try:
        last = next((m for m in reversed(history or []) if str(m.get("role")).lower() == "assistant"), None)
        last_text = (last.get("content") or "").lower() if last else ""
    except Exception:
        last_text = ""
    options = [t for t in pool if (t.lower() not in last_text)] or pool
    return _rnd.choice(options)


# --- Desambiguación de nombres cortos ---
_STOP_TOKENS = {
    "quien", "quién", "que", "qué", "hace", "de", "la", "el", "un", "una", "los", "las",
    "del", "al", "su", "sus", "es", "soy", "eres", "anda", "hola", "buenas", "buenos",
}


def _maybe_disambiguate_person(q: str | None) -> str | None:
    s = (q or "").strip()
    if not s:
        return None
    # extrae palabras alfabéticas
    words = [w.lower() for w in re.findall(r"[a-zA-ZÁÉÍÓÚÑáéíóúñ]+", s)]
    core = [w for w in words if w not in _STOP_TOKENS]
    if not core:
        return None
    # si solo hay un token significativo (posible nombre sin apellido), pide apellido/rol
    if len(core) == 1 and len(core[0]) >= 3:
        name = core[0].capitalize()
        return (
            f"¿Te refieres a {name}? Para ayudarte mejor, ¿puedes compartir su apellido y si es profesor, estudiante o administrativo?"
        )
    return None


def _looks_like_person_name(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    toks = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", s)
    # nombre de 2+ tokens alfabeticos y sin números → probable persona
    return len(toks) >= 2


def _bias_people_query(q: str, history: list[dict] | None) -> str:
    s = q or ""
    low = s.lower()
    if not _looks_like_person_name(s):
        return s
    role_words = ("profesor" in low or "profesora" in low or "profe" in low or "maestro" in low or "jefe" in low or "doctor" in low)
    if role_words:
        return s
    # Si el usuario dijo antes "al profesor" u otro rol, úsalo
    last_user = ""
    try:
        for m in reversed(history or []):
            if str(m.get("role") or "").lower() == "user":
                last_user = (m.get("content") or "").lower()
                break
    except Exception:
        last_user = ""
    if any(w in last_user for w in ("profesor", "profesora", "profe", "maestro", "jefe", "doctor")):
        return f"{s} ({last_user})"
    # Añade sesgo neutro hacia perfiles académicos de UABCS
    extra = "perfil académico UABCS, profesor/docente/jefe de departamento/doctor"
    if "dasc" in low:
        extra += ", Departamento Académico de Sistemas Computacionales (DASC)"
    if ("jefe" in low and "depart" in low):
        extra += ", jefatura/director de departamento"
    return f"{s} ({extra})"


def _last_assistant_text(history: list[dict] | None) -> str:
    try:
        if not history:
            return ""
        last = next((m for m in reversed(history) if str(m.get("role")).lower() == "assistant"), None)
        return (last.get("content") or "") if last else ""
    except Exception:
        return ""


def _last_topic(history: list[dict] | None) -> str | None:
    txt = _last_assistant_text(history)
    return _detect_topic("", txt) if txt else None


def _infer_followup_attribute(q: str, history: list[dict] | None) -> str:
    """Si el último tema fue 'contacto' (correo) y el usuario dice
    'ahora el de <nombre>' o 'el de <nombre>', asume que pide correo.
    """
    topic = _last_topic(history)
    if topic != "contacto":
        return q
    s = q or ""
    low = s.lower()
    # Si ya menciona correo/email, no tocar
    if re.search(r"\b(correo|email|e-?mail|mail)\b", low):
        return q
    # Patrones de continuación: "ahora el de Teresita", "y el del profe Soto"
    m = re.search(
        r"\b(?:ahora|y|tamb[ií]en)?\s*el\s+d[e]l?\s*(profe|profesor(?:a)?|maestro|doctor(?:a)?)?\s*"
        r"([A-Za-zÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-Za-zÁÉÍÓÚÑáéíóúñ]+){0,3})\b",
        s,
        re.IGNORECASE,
    )
    if m:
        role = (m.group(1) or "").strip().lower()
        name = m.group(2).strip()
        role_norm = "profesor" if role in ("", None, "profe", "profesora", "maestra") else role
        return f"correo del {role_norm} {name}"
    # Si solo menciona un nombre (1–3 tokens) tras pedir correo antes
    toks = [t for t in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", s) if t.lower() not in {"ahora","el","del","de","la","y","tambien","también","profe","profesor","profesora","maestro","doctor","doctora"}]
    if 1 <= len(toks) <= 3:
        name = " ".join(toks)
        return f"correo del profesor {name.strip()}"
    return q


def _offer_code_for(question: str, answer: str, topic: str | None) -> str | None:
    if not topic:
        return None
    if topic == "asueto":
        return "offer_asuetos_next_month"
    if topic == "fin":
        return "offer_exam_dates"
    if topic == "calendario":
        return "offer_open_pdf"
    if topic == "inicio":
        return "offer_reinscripciones"
    return None


# --- Heurística para referencias con pronombres ("su correo") ---
_NAME_RE = re.compile(r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,4})")

def _normalize_name_case(name: str) -> str:
    try:
        parts = [p for p in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", name) if p]
        return " ".join(p.capitalize() for p in parts)
    except Exception:
        return name


def _last_person_from_history(history: list[dict] | None) -> str | None:
    if not history:
        return None
    # Revisa los últimos 6 mensajes (assistant y user) para encontrar el último nombre
    msgs: list[str] = []
    try:
        for m in reversed(history[-6:]):
            c = str(m.get("content") or "")
            if c:
                msgs.append(c)
    except Exception:
        pass
    # 1) Busca patrón con rol + nombre: "profe/maestro/profesor/doctora <nombre>"
    role_pat = re.compile(r"\b(profe|profesor(?:a)?|maestro|doctor(?:a)?)\s+([A-Za-zÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-Za-zÁÉÍÓÚÑáéíóúñ]+){0,4})", re.IGNORECASE)
    for t in msgs:
        rm = list(role_pat.finditer(t))
        if rm:
            name = rm[-1].group(2)
            return _normalize_name_case(name)
    # 2) Busca nombre con mayúsculas
    for t in msgs:
        m = _NAME_RE.search(t)
        if m:
            return _normalize_name_case(m.group(1))
    # 3) Último token de 1–2 palabras que parezca nombre (en minúsculas), p. ej. "italia"
    simple_pat = re.compile(r"\b([a-záéíóúñ]{3,}(?:\s+[a-záéíóúñ]{3,}){0,1})\b")
    for t in msgs:
        sm = list(simple_pat.finditer(t.lower()))
        if sm:
            return _normalize_name_case(sm[-1].group(1))
    return None


def _augment_query_with_last_person(q: str, history: list[dict] | None) -> str:
    s = q or ""
    low = s.lower()
    # Activa cuando hay pronombres referenciales o pregunta de atributo genérico
    pron = (" su " in f" {low} " or low.startswith("dame su") or low.startswith("su ") or "de él" in low or "de ella" in low)
    attr = any(w in low for w in ("correo", "email", "e-mail", "contacto", "especiali", "área", "area", "materia", "materias", "que hace", "qué hace", "quien es", "quién es", "perfil"))
    if not (pron or attr):
        return s
    # Si ya hay un nombre explícito en la misma pregunta, no tocar
    if _looks_like_person_name(s):
        return s
    name = _last_person_from_history(history)
    if not name:
        return s
    return f"{s} (del profesor {name})"


# --- Utilidades de preprocesamiento temporal y limpieza de citas ---

_MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def _now_local(user_email: str | None) -> datetime:
    tz = None
    try:
        tz = get_user_tz(user_email)
    except Exception:
        tz = None
    try:
        return datetime.now(ZoneInfo(tz)) if tz else datetime.now()
    except Exception:
        return datetime.now()


def _rewrite_temporal_phrases(q: str, user_email: str | None) -> str:
    s = (q or "")
    low = s.lower()
    if "este mes" in low or "mes actual" in low:
        d = _now_local(user_email)
        mes = _MONTHS_ES.get(d.month, str(d.month))
        reemplazo = f"{mes} de {d.year}"
        s = re.sub(r"(?i)en\s+este\s+mes", f"en {reemplazo}", s)
        s = re.sub(r"(?i)este\s+mes", reemplazo, s)
        s = re.sub(r"(?i)el\s+mes\s+actual", f"el mes de {reemplazo}", s)
    return s


_CITATION_RE = re.compile(r"\((?:calendario|Calendario)[^\)]*\)$")


def _strip_citations(text: str) -> str:
    if not text:
        return text
    out = text
    # Elimina paréntesis con 'Calendario ...' en cualquier parte del texto
    out = re.sub(r"\s*\((?i:calendario)[^\)]*\)\s*", " ", out).strip()
    # También elimina la variante final si quedó
    out = re.sub(_CITATION_RE, "", out).strip()
    return out


def _strip_markdown_styles(text: str) -> str:
    """Elimina marcadores Markdown básicos (negritas/itálicas/código)."""
    if not text:
        return text
    out = text
    # **bold** y __bold__
    out = re.sub(r"\*\*([^\*\n]+)\*\*", r"\1", out)
    out = re.sub(r"__([^_\n]+)__", r"\1", out)
    # *italic* y _italic_
    out = re.sub(r"\*([^\*\n]+)\*", r"\1", out)
    out = re.sub(r"_([^_\n]+)_", r"\1", out)
    # `code`
    out = re.sub(r"`([^`]+)`", r"\1", out)
    return out


def _clean_text(text: str) -> str:
    return _strip_markdown_styles(_strip_citations(text or ""))


_CONTACT_RE = re.compile(r"\b(correo|email|e-?mail|mail)\b", re.IGNORECASE)


def _strip_irrelevant_contact(ans: str, question: str) -> str:
    """Si la pregunta no es sobre correo/email, elimina frases sobre correo.

    Evita que, tras cambiar de tema (p. ej., calendario), el modelo arrastre
    menciones al correo del profesor del turno anterior.
    """
    try:
        if _CONTACT_RE.search(question or ""):
            return ans
        # Divide por oraciones simples y filtra las que hablen de correo
        parts = re.split(r"(?<=[.!?])\s+", ans.strip())
        parts = [p for p in parts if not _CONTACT_RE.search(p)]
        out = " ".join(parts).strip()
        return out or ans
    except Exception:
        return ans


_NO_CLASSES_HINT = re.compile(r"\b(no\s+hay\s+clases|sin\s+clases|dia\s+sin\s+clases|d[ií]a\s+sin\s+clases)\b", re.IGNORECASE)


def _bias_asueto_query(q: str) -> str:
    """Si el usuario pregunta 'no hay clases', sesga la consulta hacia 'asueto/feriado/festivo'."""
    if _NO_CLASSES_HINT.search(q or ""):
        # Añade términos para guiar la recuperación hacia asuetos/feriados
        return f"{q} (asueto, feriado, festivo)"
    return q


_EXAM_HINT_RE = re.compile(r"\b(ordinari[oa]s?|extraordinari[oa]s?)\b", re.IGNORECASE)
_EXAM_WORD_RE = re.compile(r"ex[aá]men", re.IGNORECASE)


def _bias_exam_query(q: str) -> str:
    """Si el usuario menciona 'ordinarios/extraordinarios' pero no 'exámenes', añade
    términos relacionados para mejorar el recall del RAG hacia fechas de exámenes."""
    s = q or ""
    if _EXAM_HINT_RE.search(s) and not _EXAM_WORD_RE.search(s):
        return f"{s} (exámenes ordinarios, fechas de exámenes, periodo de exámenes)"
    return s


# --- Sesgo hacia "próxima fecha" si el usuario no especifica periodo ---
_MONTH_NAMES_RE = re.compile(
    r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b20\d{2}\b")
_WHEN_HINT_RE = re.compile(
    r"\b(cu[aá]ndo|cuando|fecha|fechas|proximo|pr[oó]ximo|siguiente|egreso|graduaci[oó]n|ceremonia|ex[aá]men|inscripci[oó]n|reinscripci[oó]n|vacacion|asueto|inicio de clases|fin de clases)\b",
    re.IGNORECASE,
)


def _has_explicit_period(text: str) -> bool:
    s = text or ""
    if _MONTH_NAMES_RE.search(s):
        return True
    if _YEAR_RE.search(s):
        return True
    # patrón simple "d de <mes>"
    if re.search(r"\b\d{1,2}\s+de\s+" + _MONTH_NAMES_RE.pattern, s, re.IGNORECASE):
        return True
    return False


def _format_today_es(d: datetime) -> str:
    mes = _MONTHS_ES.get(d.month, str(d.month))
    return f"{d.day} de {mes} de {d.year}"


def _bias_upcoming_query(q: str, user_email: str | None) -> str:
    """Si la pregunta sugiere fechas pero no especifica periodo, orienta a 'próxima fecha'."""
    s = q or ""
    if not _WHEN_HINT_RE.search(s):
        return s
    if _has_explicit_period(s):
        return s
    now = _now_local(user_email)
    today = _format_today_es(now)
    return f"{s} (responde con la próxima fecha a partir de hoy {today}; siguiente evento del calendario)"


# --- Continuidad: confirmaciones breves sí/no ---
AFFIRM_RE = re.compile(r"^\s*(s[ií]|va|ok|dale|claro|de acuerdo|si por favor|sí por favor|porfa|por favor)\s*[.!]?\s*$", re.IGNORECASE)
NEG_RE = re.compile(r"^\s*(no|nel|nop|no gracias)\s*[.!]?\s*$", re.IGNORECASE)


def _is_yes_or_no(text: str | None) -> bool:
    t = (text or "").strip().lower()
    return bool(AFFIRM_RE.match(t) or NEG_RE.match(t))


def _is_yes(text: str | None) -> bool:
    t = (text or "").strip().lower()
    return bool(AFFIRM_RE.match(t))


def _last_offer(history: list[dict] | None) -> str | None:
    """Detecta la última 'oferta' hecha por el asistente en el historial.

    Retorna un código simbólico que podemos accionar.
    """
    if not history:
        return None
    for m in reversed(history):
        if str(m.get("role")).lower() != "assistant":
            continue
        # Preferir código explícito guardado en citations
        cites = m.get("citations") or []
        if isinstance(cites, list):
            for c in cites:
                if isinstance(c, dict) and c.get("offer"):
                    return str(c.get("offer"))
        txt = str(m.get("content") or "").lower()
        if not txt:
            continue
        if "fechas de exámenes" in txt or "fechas de examenes" in txt:
            return "offer_exam_dates"
        if "pdf oficial" in txt or "enlace al documento" in txt:
            return "offer_open_pdf"
        if "recordar tus próximas clases" in txt or "recordarte tus próximas clases" in txt:
            return "offer_set_reminder"
        if "asuetos del próximo mes" in txt or "asuetos del proximo mes" in txt:
            return "offer_asuetos_next_month"
    return None
