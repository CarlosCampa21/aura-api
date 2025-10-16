"""
Define y aplica validadores (JSON Schema) e índices en Mongo.
Se ejecuta al inicio de la app para garantizar una base consistente.
"""
from __future__ import annotations

from typing import Any, Dict, List
from pymongo.errors import PyMongoError
from app.infrastructure.db.mongo import get_db


def _collmod_or_create(name: str, validator: Dict[str, Any] | None) -> None:
    db = get_db()
    try:
        if validator:
            # Intenta aplicar validator con collMod
            db.command({
                "collMod": name,
                "validator": {"$jsonSchema": validator},
                "validationLevel": "moderate",
            })
        else:
            # Asegura que exista la colección
            db.create_collection(name)
    except PyMongoError:
        # Si collMod falla (no existe o sin validator), intenta crear con validator
        try:
            if name not in db.list_collection_names():
                if validator:
                    db.create_collection(name, validator={"$jsonSchema": validator})
                else:
                    db.create_collection(name)
            elif validator:
                # Intento final: algunos motores no aceptan collMod sin privilegios.
                # En ese caso, seguimos sin romper el arranque.
                pass
        except PyMongoError:
            # No aborta el arranque; solo deja sin validator estricto.
            pass


def _ensure_indexes(name: str, indexes: List[Dict[str, Any]]) -> None:
    coll = get_db()[name]
    for ix in indexes:
        keys = ix.pop("keys")
        try:
            coll.create_index(keys, **ix)
        except PyMongoError:
            # Ignora fallas de índice (e.g., ya existe o datos no únicos previos)
            pass


def ensure_collections() -> None:
    """
    Garantiza colecciones, validadores e índices mínimos.
    """
    # User (autenticación local/google)
    user_validator = {
        "bsonType": "object",
        "required": [
            "email",
            "auth_provider",
            "is_active",
            "email_verified",
            "token_version",
            "created_at",
            "updated_at",
        ],
        "properties": {
            "email": {"bsonType": "string", "minLength": 3, "description": "lowercase"},
            "password_hash": {"bsonType": "string"},
            "auth_provider": {"bsonType": "string", "enum": ["local", "google"]},
            "google_id": {"bsonType": "string"},

            "is_active": {"bsonType": "bool"},
            "email_verified": {"bsonType": "bool"},
            "token_version": {"bsonType": "int", "minimum": 0},

            "profile": {
                "bsonType": "object",
                "required": [],
                "properties": {
                    "full_name": {"bsonType": "string"},
                    "student_id": {"bsonType": "string"},
                    "major": {"bsonType": "string"},
                    "semester": {"bsonType": "int", "minimum": 1},
                    "shift": {"bsonType": "string", "enum": ["TM", "TV"]},
                    "tz": {"bsonType": "string"},
                    "phone": {"bsonType": "string"},
                    "birthday": {"bsonType": "string"},
                    "preferences": {
                        "bsonType": "object",
                        "properties": {
                            "language": {"bsonType": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": True,
            },

            "created_at": {"bsonType": "string", "minLength": 10},
            "updated_at": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
        # Reglas condicionales según el proveedor de autenticación
        "allOf": [
            {
                "if": {"properties": {"auth_provider": {"const": "local"}}},
                "then": {"required": ["password_hash"]},
            },
            {
                "if": {"properties": {"auth_provider": {"const": "google"}}},
                "then": {"required": ["google_id"]},
            },
        ],
    }
    _collmod_or_create("user", user_validator)
    _ensure_indexes(
        "user",
        [
            {"keys": [("email", 1)], "unique": True, "name": "uniq_email"},
            {"keys": [("profile.student_id", 1)], "name": "ix_student_id"},
        ],
    )

    # Materias (catálogo)
    materias_validator = {
        "bsonType": "object",
        "required": ["codigo", "nombre", "profesor", "salon"],
        "properties": {
            "codigo": {"bsonType": "string", "minLength": 1},
            "nombre": {"bsonType": "string", "minLength": 1},
            "profesor": {"bsonType": "string", "minLength": 1},
            "salon": {"bsonType": "string", "minLength": 1},
            "dias": {"bsonType": "array", "items": {"bsonType": "string"}},
            "hora_inicio": {"bsonType": "string"},
            "hora_fin": {"bsonType": "string"},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("materias", materias_validator)
    _ensure_indexes(
        "materias",
        [
            {"keys": [("codigo", 1)], "unique": True, "name": "uniq_codigo"},
        ],
    )

    # Horarios (para consultas por usuario + día + hora)
    # Día admite nombres comunes en español (corto/largo, con/sin acento) para compatibilidad
    horarios_validator = {
        "bsonType": "object",
        "required": ["usuario_correo", "materia_codigo", "dia", "hora_inicio", "hora_fin"],
        "properties": {
            "usuario_correo": {"bsonType": "string", "minLength": 3},
            "materia_codigo": {"bsonType": "string", "minLength": 1},
            "dia": {
                "bsonType": "string",
                "enum": [
                    "Lunes", "Martes", "Miercoles", "Miércoles", "Jueves", "Viernes", "Sabado", "Sábado", "Domingo",
                    "Lun", "Mar", "Mie", "Mié", "Jue", "Vie", "Sab", "Sáb", "Dom",
                ],
            },
            "hora_inicio": {"bsonType": "string", "pattern": "^\\d{2}:\\d{2}$"},
            "hora_fin": {"bsonType": "string", "pattern": "^\\d{2}:\\d{2}$"},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("horarios", horarios_validator)
    _ensure_indexes(
        "horarios",
        [
            {"keys": [("usuario_correo", 1)], "name": "ix_horarios_user"},
            {"keys": [("usuario_correo", 1), ("dia", 1), ("hora_inicio", 1)], "name": "ix_user_dia_inicio"},
        ],
    )

    # Notas (por usuario y created_at)
    notas_validator = {
        "bsonType": "object",
        "required": ["usuario_correo", "titulo", "contenido", "tags", "created_at"],
        "properties": {
            "usuario_correo": {"bsonType": "string", "minLength": 3},
            "titulo": {"bsonType": "string", "minLength": 1},
            "contenido": {"bsonType": "string", "minLength": 1},
            "tags": {"bsonType": "array", "items": {"bsonType": "string"}},
            "created_at": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("notas", notas_validator)
    _ensure_indexes(
        "notas",
        [
            {"keys": [("usuario_correo", 1)], "name": "ix_notas_user"},
            {"keys": [("usuario_correo", 1), ("created_at", -1)], "name": "ix_user_created"},
        ],
    )

    # Consultas (histórico de preguntas/respuestas)
    consultas_validator = {
        "bsonType": "object",
        "required": ["usuario_correo", "pregunta", "respuesta", "ts"],
        "properties": {
            "usuario_correo": {"bsonType": "string", "minLength": 3},
            "pregunta": {"bsonType": "string", "minLength": 1},
            "respuesta": {"bsonType": "string"},
            "ts": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("consultas", consultas_validator)
    _ensure_indexes(
        "consultas",
        [
            {"keys": [("usuario_correo", 1)], "name": "ix_consultas_user"},
            {"keys": [("usuario_correo", 1), ("ts", -1)], "name": "ix_user_ts"},
        ],
    )
