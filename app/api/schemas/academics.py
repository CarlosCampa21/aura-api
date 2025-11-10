"""
Esquemas Pydantic para componentes académicos (horarios) del DASC.

Convenciones:
- Campos en inglés y snake_case.
- Comentarios en español.
- Timestamps ISO-8601 UTC sellados en repositorios.
"""
from typing import Optional, Literal, List
from pydantic import BaseModel, Field, field_validator


Day = Literal["mon", "tue", "wed", "thu", "fri", "sat"]


class DepartmentCreate(BaseModel):
    code: str  # DASC
    name: str
    campus: Optional[str] = None


class DepartmentOut(BaseModel):
    code: str
    name: str
    campus: Optional[str] = None
    created_at: str
    updated_at: str


class ProgramCreate(BaseModel):
    department_code: str = Field(default="DASC")
    code: str
    name: Optional[str] = None


class ProgramOut(BaseModel):
    department_code: str
    code: str
    name: Optional[str] = None
    created_at: str
    updated_at: str


class Period(BaseModel):
    code: str  # 2025-II
    year: int
    term: str  # I, II, Verano
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None
    status: Literal["planned", "active", "archived"] = "active"


class PeriodCreate(BaseModel):
    code: str
    year: int
    term: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Literal["planned", "active", "archived"] = "active"


class PeriodOut(Period):
    created_at: str
    updated_at: str


class CourseCreate(BaseModel):
    code: Optional[str] = None
    name: str
    short_name: Optional[str] = None
    credits: Optional[int] = None


class CourseOut(BaseModel):
    code: Optional[str] = None
    name: str
    short_name: Optional[str] = None
    credits: Optional[int] = None
    created_at: str
    updated_at: str


class TimetableCreate(BaseModel):
    department_code: str = Field(default="DASC")
    program_code: str
    semester: int
    group: str = Field(default="A")
    period_code: str
    shift: Optional[Literal["TM", "TV"]] = None  # Si falta, se infiere por entradas
    title: Optional[str] = None
    notes: Optional[str] = None


class TimetableOut(BaseModel):
    department_code: str
    program_code: str
    semester: int
    group: str
    period_code: str
    shift: Optional[Literal["TM", "TV"]] = None
    title: str
    status: Literal["draft", "published", "archived"]
    version: int
    is_current: bool
    created_at: str
    updated_at: str
    published_at: Optional[str] = None


class TimetableEntryCreate(BaseModel):
    timetable_id: str
    day: Day
    start_time: str  # HH:MM 24h
    end_time: str
    course_name: str
    instructor: Optional[str] = None
    room_code: Optional[str] = None
    modality: Literal["class", "lab", "seminar", "other"] = "class"
    module: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("start_time", "end_time")
    @classmethod
    def _validate_time(cls, v: str) -> str:
        if len(v) == 5 and v[2] == ":" and v[:2].isdigit() and v[3:].isdigit():
            return v
        raise ValueError("time must be HH:MM")


class TimetableEntryOut(BaseModel):
    timetable_id: str
    day: Day
    start_time: str
    end_time: str
    course_name: str
    instructor: Optional[str] = None
    room_code: Optional[str] = None
    modality: Literal["class", "lab", "seminar", "other"]
    module: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    updated_at: str


# ---- Import/Upsert combinado ----
class TimetableImportEntry(BaseModel):
    day: Day
    start_time: str
    end_time: str
    course_name: str
    instructor: Optional[str] = None
    room_code: Optional[str] = None
    modality: Literal["class", "lab", "seminar", "other"] = "class"
    module: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("start_time", "end_time")
    @classmethod
    def _validate_time2(cls, v: str) -> str:
        if len(v) == 5 and v[2] == ":" and v[:2].isdigit() and v[3:].isdigit():
            return v
        raise ValueError("time must be HH:MM")


class TimetableImportRequest(BaseModel):
    department_code: str = Field(default="DASC")
    program_code: str
    semester: int
    group: str = Field(default="A")
    period_code: str
    shift: Optional[Literal["TM", "TV"]] = None
    title: Optional[str] = None
    ensure_catalogs: bool = True
    publish: bool = True
    replace_entries: bool = True
    entries: List[TimetableImportEntry]
