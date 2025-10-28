"""
Service layer for notes: thin wrappers over repositories.
"""
from typing import Dict, Any, List, Optional

from app.repositories.note_repo import (
    insert_note as _insert_note,
    list_notes as _list_notes,
)


def insert_note(doc: Dict[str, Any]) -> str:
    return _insert_note(doc)


def list_notes(user_id: Optional[str] = None, status: Optional[str] = None, tag: Optional[str] = None) -> List[Dict[str, Any]]:
    return _list_notes(user_id=user_id, status=status, tag=tag)

