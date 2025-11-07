"""Easter eggs de AURA: detección simple por patrones.

Este módulo permite responder de forma divertida a ciertos *triggers* sin
pasar por RAG ni por el LLM. Mantén los patrones específicos y con anclas
para evitar falsos positivos.
"""
from __future__ import annotations

import re
from typing import Optional, Dict, Any
import unicodedata


# Define aquí los easter eggs. Cada entrada es (regex, respuesta, adjuntos opcionales)
_EGGS: list[dict[str, object]] = [
    {
        "pattern": re.compile(r"(?i)^(di|dime)?\s*so!?$"),
        "answer": "so 😂 👉 jajajaja",
    },
    {
        "pattern": re.compile(r"(?i)konami|↑\s*↑\s*↓\s*↓\s*←\s*→\s*←\s*→\s*b\s*a"),
        "answer": "Desbloqueaste el modo secreto 🎮",
    },
    {
        "pattern": re.compile(r"(?i)^hola\s+mcfly$"),
        "answer": "¿Hay alguien en casa? 👋",
    },
    {
        "pattern": re.compile(r"(?i)rickroll"),
        "answer": "Nunca te abandonaré: https://youtu.be/dQw4w9WgXcQ",
        "attachments": ["https://youtu.be/dQw4w9WgXcQ"],
    },
    {
        "pattern": re.compile(r"(?i)\b(pastilla|píldora)\b.*\b(azul|roja)\b|\bazul o roja\b"),
        "answer": "Tomas la azul y sigues con tu día; tomas la roja y te muestro qué hay en el calendario. 😉",
    },
]


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def check_easter_egg(question: str | None, history: list[dict] | None = None) -> Optional[Dict[str, Any]]:
    """Devuelve una respuesta de easter egg si el prompt coincide con algún patrón.

    Estructura compatible con la salida de ask_service.ask para integrarse sin cambios.
    """
    s = (question or "").strip()
    if not s:
        return None
    # Normalización simple para variantes (acentos y equivalentes coloquiales)
    norm = _strip_accents(s).lower()
    # Captura directa de "que/qué/ke/k/q" con o sin prefijos "di|dime" y signos finales
    if re.match(r"^(?:di\s+|dime\s+)?(?:que|ke|k|q)\s*[.!?]*$", norm):
        return {
            "pregunta": question,
            "respuesta": "SO 😂 👉 JAJAJAJA",
            "contexto_usado": False,
            "came_from": "easter-egg",
            "citation": "",
            "source_chunks": [],
            "followup": "",
            "attachments": [],
        }

    for egg in _EGGS:
        pat = egg["pattern"]  # type: ignore[assignment]
        if isinstance(pat, re.Pattern) and pat.search(s):
            text = str(egg.get("answer") or "")
            attachments = list(egg.get("attachments") or [])
            return {
                "pregunta": question,
                "respuesta": text,
                "contexto_usado": False,
                "came_from": "easter-egg",
                "citation": "",
                "source_chunks": [],
                "followup": "",
                "attachments": attachments,
            }
    return None
