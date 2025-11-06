"""Memoria conversacional ligera: resumen incremental y foco de entidad.

No guarda todo el historial; mantiene un `summary` y un `entity_focus`
persistidos en `conversations.metadata` para guiar respuestas encadenadas.
"""
from __future__ import annotations

import re
from typing import Optional, List, Dict

from app.infrastructure.ai.openai_client import get_openai


_NAME_RE = re.compile(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})\b")


def extract_person_name(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    m = None
    for m in _NAME_RE.finditer(text):
        pass
    return m.group(1) if m else None


def choose_entity_focus(prev_messages: Optional[List[Dict]], question: str, answer: str) -> Optional[str]:
    """Elige el foco de entidad buscando el último nombre propio razonable.

    Prioridad: nombre en la pregunta > nombre en la respuesta > nombres en los
    últimos turnos previos.
    """
    # 1) pregunta
    n = extract_person_name(question)
    if n:
        return n
    # 2) respuesta
    n = extract_person_name(answer)
    if n:
        return n
    # 3) historial reciente
    if prev_messages:
        tail = list(prev_messages)[-6:]
        for msg in reversed(tail):
            n = extract_person_name(str(msg.get("content") or ""))
            if n:
                return n
    return None


def summarize_incremental(prev_summary: Optional[str], question: str, answer: str) -> str:
    """Genera un resumen breve (1–2 oraciones) de la conversación.

    Usa OpenAI si está disponible; si no, fallback a concatenación limitada.
    """
    oa = get_openai()
    prev = (prev_summary or "").strip()
    if oa:
        prompt = (
            "Eres un asistente que mantiene un resumen conciso (1–2 oraciones) "
            "de una conversación entre un alumno y AURA. Actualiza el resumen "
            "incorporando el último intercambio. Evita detalles innecesarios.\n\n"
            f"Resumen previo: {prev or '(vacío)'}\n"
            f"Alumno: {question}\n"
            f"AURA: {answer}\n"
            "Nuevo resumen:"
        )
        try:
            resp = oa.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            out = (resp.choices[0].message.content or "").strip()
            # Limita tamaño por seguridad
            return out[:400]
        except Exception:
            pass
    # Fallback simple
    base = (prev + " ") if prev else ""
    summary = (base + f"Alumno pregunta sobre '{question[:60]}'; AURA responde '{answer[:60]}'.").strip()
    return summary[:400]

