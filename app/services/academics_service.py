"""Servicios académicos: envoltorios delgados sobre repos para mantener routers limpios."""
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
    """Inserta timetable y devuelve id."""
    return _insert_timetable(doc)


def list_timetables(filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Lista timetables según filtros básicos."""
    return _list_timetables(filters)


def publish_timetable(timetable_id: str) -> None:
    """Publica timetable y marca como current en su combinación."""
    return _publish_timetable(timetable_id)


def insert_entries_bulk(timetable_id: str, entries: List[Dict[str, Any]]) -> int:
    """Inserta entries en bloque y devuelve cantidad insertada."""
    return _insert_entries_bulk(timetable_id, entries)


def list_entries(timetable_id: str) -> List[Dict[str, Any]]:
    """Lista entries de un timetable."""
    return _list_entries(timetable_id)


def insert_department(doc: Dict[str, Any]) -> str:
    """Inserta department y devuelve id."""
    return _insert_department(doc)


def list_departments() -> List[Dict[str, Any]]:
    """Lista departments."""
    return _list_departments()


def insert_program(doc: Dict[str, Any]) -> str:
    """Inserta program y devuelve id."""
    return _insert_program(doc)


def list_programs(department_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista programs (opcionalmente por department_code)."""
    return _list_programs(department_code)


def insert_period(doc: Dict[str, Any]) -> str:
    """Inserta period y devuelve id."""
    return _insert_period(doc)


def list_periods(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista periods (filtrable por status)."""
    return _list_periods(status)


def insert_course(doc: Dict[str, Any]) -> str:
    """Inserta course y devuelve id."""
    return _insert_course(doc)


def list_courses() -> List[Dict[str, Any]]:
    """Lista courses."""
    return _list_courses()
