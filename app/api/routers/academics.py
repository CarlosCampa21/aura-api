"""Endpoints para horarios académicos: timetables, entries y catálogos."""
from fastapi import APIRouter, HTTPException, status, Query
from typing import Optional, List, Dict, Any, Literal
from app.api.schemas.academics import (
    TimetableCreate,
    TimetableOut,
    TimetableEntryCreate,
    TimetableEntryOut,
    TimetableImportRequest,
)
from app.services.academics_service import (
    insert_timetable,
    list_timetables,
    publish_timetable,
    insert_entries_bulk,
    list_entries,
    insert_department,
    list_departments,
    insert_program,
    list_programs,
    insert_period,
    list_periods,
    insert_course,
    list_courses,
)
from app.infrastructure.db.mongo import get_db
from app.api.schemas.academics import (
    DepartmentCreate,
    DepartmentOut,
    ProgramCreate,
    ProgramOut,
    PeriodCreate,
    PeriodOut,
    CourseCreate,
    CourseOut,
)

router = APIRouter(prefix="/academics", tags=["Academics"])

@router.post(
    "/timetables",
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
    summary="Crear timetable",
    description="Crea un horario académico con metadatos básicos.",
)
def create_timetable(payload: TimetableCreate):
    try:
        inserted_id = insert_timetable(payload.model_dump(mode="json"))
        out = TimetableOut(
            department_code=payload.department_code,
            program_code=payload.program_code,
            semester=payload.semester,
            group=payload.group,
            period_code=payload.period_code,
            shift=payload.shift,
            title=payload.title or "",
            status="draft",
            version=1,
            is_current=False,
            created_at="",
            updated_at="",
            published_at=None,
        ).model_dump()
        return {"message": "ok", "id": inserted_id, "data": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo crear el horario: {e}")


@router.get(
    "/timetables",
    response_model=dict,
    summary="Listar timetables",
    description="Lista horarios filtrando por programa/semestre/grupo/período.",
)
def get_timetables(
    department_code: Optional[str] = Query(default="DASC", description="Código de departamento (p.ej., DASC)"),
    program_code: Optional[str] = Query(default=None, description="Programa (p.ej., IDS, ITC)"),
    semester: Optional[int] = Query(default=None, ge=1, description="Semestre numérico (>=1)"),
    group: Optional[str] = Query(default=None, min_length=1, max_length=3, description="Grupo (p.ej., A, B)"),
    period_code: Optional[str] = Query(default=None, description="Código de período (p.ej., 2025-II)"),
    status_f: Optional[Literal["draft", "published", "archived"]] = Query(default=None, description="Estado del timetable"),
    is_current: Optional[bool] = Query(default=None, description="Si es el timetable vigente"),
    shift: Optional[Literal["TM", "TV"]] = Query(default=None, description="Turno TM/TV"),
):
    try:
        items = list_timetables({
            "department_code": department_code,
            "program_code": program_code,
            "semester": semester,
            "group": group,
            "period_code": period_code,
            "status": status_f,
            "is_current": is_current,
            "shift": shift,
        })
        return {"timetables": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron listar los horarios: {e}")


@router.post("/timetables/{timetable_id}/publish", response_model=dict)
def publish(timetable_id: str):
    try:
        publish_timetable(timetable_id)
        return {"message": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo publicar el horario: {e}")


@router.post(
    "/timetable-entries",
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
    summary="Insertar entries en bloque",
    description="Inserta múltiples entries para un timetable.",
)
def create_entries(payload: Dict[str, Any]):
    """
    Inserta entradas en bloque para un `timetable_id`.
    payload: { timetable_id: str, entries: TimetableEntryCreate[] }
    """
    try:
        timetable_id = str(payload.get("timetable_id"))
        entries: List[Dict[str, Any]] = payload.get("entries") or []
        # Validación Pydantic por elemento
        normalized: List[Dict[str, Any]] = []
        for e in entries:
            obj = TimetableEntryCreate(**{**e, "timetable_id": timetable_id})
            normalized.append(obj.model_dump(mode="json"))
        count = insert_entries_bulk(timetable_id, normalized)
        return {"inserted": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron crear las entradas del horario: {e}")


@router.get(
    "/timetable-entries",
    response_model=dict,
    summary="Listar entries de un timetable",
    description="Devuelve las entries de un horario por su id.",
)
def get_entries(timetable_id: str = Query(...)):
    try:
        items = list_entries(timetable_id)
        return {"entries": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron listar las entradas del horario: {e}")


@router.post(
    "/timetables/import",
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
    summary="Crear/actualizar timetable con entries (todo en uno)",
    description="Crea o reutiliza el timetable por combinación y reemplaza sus entries. Opcionalmente publica y asegura catálogos.",
)
def import_timetable(payload: TimetableImportRequest):
    try:
        db = get_db()
        # Asegura catálogos si aplica
        if payload.ensure_catalogs:
            if not db["department"].find_one({"code": payload.department_code}):
                insert_department({"code": payload.department_code, "name": payload.department_code})
            if not db["program"].find_one({"department_code": payload.department_code, "code": payload.program_code}):
                insert_program({"department_code": payload.department_code, "code": payload.program_code, "name": payload.program_code})
            if not db["period"].find_one({"code": payload.period_code}):
                insert_period({"code": payload.period_code, "year": 0, "term": payload.period_code, "status": "active"})

        existing = db["timetable"].find_one({
            "department_code": payload.department_code,
            "program_code": payload.program_code,
            "semester": payload.semester,
            "group": payload.group,
            "period_code": payload.period_code,
            **({"shift": payload.shift} if payload.shift else {}),
        })
        if existing:
            tid = str(existing["_id"])
        else:
            tid = insert_timetable({
                "department_code": payload.department_code,
                "program_code": payload.program_code,
                "semester": payload.semester,
                "group": payload.group,
                "period_code": payload.period_code,
                "shift": payload.shift,
                "title": payload.title,
            })

        if payload.replace_entries:
            db["timetable_entry"].delete_many({"timetable_id": tid})

        # Normaliza entries
        items: list[dict] = []
        for e in payload.entries:
            d = TimetableEntryCreate(
                timetable_id=tid,
                day=e.day,
                start_time=e.start_time,
                end_time=e.end_time,
                course_name=e.course_name,
                instructor=e.instructor,
                room_code=e.room_code,
                modality=e.modality,
                module=e.module,
                notes=e.notes,
            ).model_dump(mode="json")
            items.append(d)
        n = insert_entries_bulk(tid, items)

        if payload.publish:
            publish_timetable(tid)

        return {"message": "ok", "timetable_id": tid, "entries_inserted": n, "published": bool(payload.publish)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo importar el horario: {e}")


# ---- Catálogos ----

@router.post("/departments", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_department(payload: DepartmentCreate):
    try:
        inserted_id = insert_department(payload.model_dump(mode="json"))
        out = DepartmentOut(
            code=payload.code,
            name=payload.name,
            campus=payload.campus,
            created_at="",
            updated_at="",
        ).model_dump()
        return {"message": "ok", "id": inserted_id, "data": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo crear el departamento: {e}")


@router.get("/departments", response_model=dict)
def get_departments():
    try:
        return {"departments": list_departments()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron listar los departamentos: {e}")


@router.post("/programs", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_program(payload: ProgramCreate):
    try:
        inserted_id = insert_program(payload.model_dump(mode="json"))
        out = ProgramOut(
            department_code=payload.department_code,
            code=payload.code,
            name=payload.name,
            created_at="",
            updated_at="",
        ).model_dump()
        return {"message": "ok", "id": inserted_id, "data": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo crear el programa: {e}")


@router.get("/programs", response_model=dict)
def get_programs(department_code: Optional[str] = Query(default=None)):
    try:
        return {"programs": list_programs(department_code)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron listar los programas: {e}")


@router.post("/periods", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_period(payload: PeriodCreate):
    try:
        inserted_id = insert_period(payload.model_dump(mode="json"))
        out = PeriodOut(**payload.model_dump(), created_at="", updated_at="").model_dump()
        return {"message": "ok", "id": inserted_id, "data": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo crear el período: {e}")


@router.get("/periods", response_model=dict)
def get_periods(status_f: Optional[str] = Query(default=None)):
    try:
        return {"periods": list_periods(status=status_f)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron listar los períodos: {e}")


@router.post("/courses", status_code=status.HTTP_201_CREATED, response_model=dict)
def create_course(payload: CourseCreate):
    try:
        inserted_id = insert_course(payload.model_dump(mode="json"))
        out = CourseOut(
            code=payload.code,
            name=payload.name,
            short_name=payload.short_name,
            credits=payload.credits,
            created_at="",
            updated_at="",
        ).model_dump()
        return {"message": "ok", "id": inserted_id, "data": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo crear el curso: {e}")


@router.get("/courses", response_model=dict)
def get_courses():
    try:
        return {"courses": list_courses()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudieron listar los cursos: {e}")
