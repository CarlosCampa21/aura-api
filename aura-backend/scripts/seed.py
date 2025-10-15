"""
Seed de datos mínimos para Aura (MongoDB).

Inserta datos de ejemplo en las colecciones:
- usuarios
- materias
- horarios

Ejecuta desde la raíz del repo con:
    PYTHONPATH=AURA/aura-backend python AURA/aura-backend/scripts/seed.py

O usando Makefile: `make seed`
"""
from datetime import datetime
from typing import List, Dict
from app.infrastructure.db.mongo import init_mongo, get_db


USUARIOS: List[Dict] = [
    {
        "correo": "jose@example.com",
        "nombre": "José Mendoza",
        "carrera": "Ingeniería en Sistemas",
        "semestre": 3,
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "correo": "ana@example.com",
        "nombre": "Ana Pérez",
        "carrera": "Administración",
        "semestre": 5,
        "created_at": datetime.utcnow().isoformat(),
    },
]

MATERIAS: List[Dict] = [
    {
        "codigo": "MAT101",
        "nombre": "Álgebra Básica",
        "profesor": "M. López",
        "salon": "B-201",
    },
    {
        "codigo": "INF201",
        "nombre": "Programación I",
        "profesor": "L. García",
        "salon": "Lab-1",
    },
    {
        "codigo": "HIS110",
        "nombre": "Historia Universal",
        "profesor": "C. Romero",
        "salon": "A-102",
    },
]

# Horarios por usuario (ejemplo reducido)
HORARIOS_JOSE: List[Dict] = [
    {"usuario_correo": "jose@example.com", "materia_codigo": "MAT101", "dia": "Lunes", "hora_inicio": "08:00", "hora_fin": "09:30"},
    {"usuario_correo": "jose@example.com", "materia_codigo": "INF201", "dia": "Martes", "hora_inicio": "10:00", "hora_fin": "12:00"},
    {"usuario_correo": "jose@example.com", "materia_codigo": "HIS110", "dia": "Jueves", "hora_inicio": "09:00", "hora_fin": "10:30"},
]

HORARIOS_ANA: List[Dict] = [
    {"usuario_correo": "ana@example.com", "materia_codigo": "HIS110", "dia": "Lunes", "hora_inicio": "11:00", "hora_fin": "12:30"},
]


def seed():
    init_mongo()
    db = get_db()

    # Limpia colecciones objetivo (idempotente para demo)
    db["usuarios"].delete_many({})
    db["materias"].delete_many({})
    db["horarios"].delete_many({})

    if USUARIOS:
        db["usuarios"].insert_many(USUARIOS)
    if MATERIAS:
        db["materias"].insert_many(MATERIAS)
    horarios_all = HORARIOS_JOSE + HORARIOS_ANA
    if horarios_all:
        db["horarios"].insert_many(horarios_all)

    # Índices útiles
    db["usuarios"].create_index("correo", unique=True)
    db["materias"].create_index("codigo", unique=True)
    db["horarios"].create_index([("usuario_correo", 1), ("materia_codigo", 1), ("dia", 1)])

    print("Seed completado:")
    print(f"  usuarios:  {db['usuarios'].count_documents({})}")
    print(f"  materias:  {db['materias'].count_documents({})}")
    print(f"  horarios:  {db['horarios'].count_documents({})}")


if __name__ == "__main__":
    seed()

