"""
Semilla de catálogos académicos (DASC y sus programas).

Uso:
  PYTHONPATH=. python scripts/seed_dasc_catalog.py

Inserta si no existen:
  - Department DASC
  - Programs: IDS, ITC, IC, LATI, LITI
"""

from app.repositories.academics_catalog_repo import (
    insert_department,
    insert_program,
)
from app.infrastructure.db.mongo import init_mongo, get_db
from app.infrastructure.db.bootstrap import ensure_collections


def upsert_department(code: str, name: str, campus: str | None = None):
    db = get_db()
    if not db["department"].find_one({"code": code}):
        insert_department({"code": code, "name": name, "campus": campus})


def upsert_program(department_code: str, code: str, name: str):
    db = get_db()
    if not db["program"].find_one({"department_code": department_code, "code": code}):
        insert_program({"department_code": department_code, "code": code, "name": name})


def main():
    init_mongo()
    ensure_collections()
    upsert_department("DASC", "Departamento Académico de Sistemas Computacionales")
    upsert_program("DASC", "IDS", "INGENIERO EN DESARROLLO DE SOFTWARE")
    upsert_program("DASC", "ITC", "INGENIERO EN TECNOLOGÍA COMPUTACIONAL")
    upsert_program("DASC", "IC", "INGENIERO EN CIBERSEGURIDAD")
    upsert_program("DASC", "LATI", "LICENCIADO EN ADMINISTRACIÓN DE TECNOLOGÍAS DE LA INFORMACIÓN")
    upsert_program("DASC", "LITI", "LICENCIADO EN TECNOLOGÍAS DE LA INFORMACIÓN")
    print("Catálogo DASC listo.")


if __name__ == "__main__":
    main()
