"""
Esquemas Pydantic para `note` (singular), alineados a convención en inglés.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator


class NoteCreate(BaseModel):
    user_id: str
    title: str
    body: str
    tags: List[str] = Field(default_factory=list)
    source: Optional[Literal["manual", "assistant", "imported"]] = "manual"
    related_conversation_id: Optional[str] = None

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, v: List[str]) -> List[str]:
        uniq = []
        seen = set()
        for t in (v or []):
            tt = t.strip().lower()
            if tt and tt not in seen:
                seen.add(tt)
                uniq.append(tt)
        return uniq


class NoteOut(BaseModel):
    user_id: str
    title: str
    body: str
    tags: List[str]
    status: Literal["active", "archived"]
    source: Literal["manual", "assistant", "imported"]
    related_conversation_id: Optional[str] = None
    created_at: str
    updated_at: str


"""
