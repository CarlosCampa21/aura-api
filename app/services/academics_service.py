"""
Service layer for academics: thin wrappers over repositories to keep routers clean.
"""
from typing import Dict, Any, List, Optional

from app.repositories.academics_timetables_repo import (
    insert_timetable as _insert_timetable,
    list_timetables as _list_timetables,
    publish_timetable as _publish_timetable,
)
from app.repositories.academics_entries_repo import (
    insert_entries_bulk as _insert_entries_bulk,
    list_entries as _list_entries,
)
from app.repositories.academics_catalog_repo import (
    insert_department as _insert_department,
    list_departments as _list_departments,
    insert_program as _insert_program,
    list_programs as _list_programs,
    insert_period as _insert_period,
    list_periods as _list_periods,
    insert_course as _insert_course,
    list_courses as _list_courses,
)


def insert_timetable(doc: Dict[str, Any]) -> str:
    return _insert_timetable(doc)


def list_timetables(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _list_timetables(filters)


def publish_timetable(timetable_id: str) -> None:
    return _publish_timetable(timetable_id)


def insert_entries_bulk(timetable_id: str, entries: List[Dict[str, Any]]) -> int:
    return _insert_entries_bulk(timetable_id, entries)


def list_entries(timetable_id: str) -> List[Dict[str, Any]]:
    return _list_entries(timetable_id)


def insert_department(doc: Dict[str, Any]) -> str:
    return _insert_department(doc)


def list_departments() -> List[Dict[str, Any]]:
    return _list_departments()


def insert_program(doc: Dict[str, Any]) -> str:
    return _insert_program(doc)


def list_programs(department_code: Optional[str] = None) -> List[Dict[str, Any]]:
    return _list_programs(department_code)


def insert_period(doc: Dict[str, Any]) -> str:
    return _insert_period(doc)


def list_periods(status: Optional[str] = None) -> List[Dict[str, Any]]:
    return _list_periods(status)


def insert_course(doc: Dict[str, Any]) -> str:
    return _insert_course(doc)


def list_courses() -> List[Dict[str, Any]]:
    return _list_courses()

