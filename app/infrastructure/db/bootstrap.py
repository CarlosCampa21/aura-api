"""
Bootstrap de la base Mongo: define y aplica validadores (JSON Schema) e índices.
Se ejecuta al inicio de la app para asegurar colecciones mínimas y consistencia.
No tumba la app si algo falla; deja warnings silenciosos en casos no críticos.
"""
from __future__ import annotations

from typing import Any, Dict, List
import logging
from pymongo.errors import PyMongoError
from app.infrastructure.db.mongo import get_db

_log = logging.getLogger("aura.mongo.bootstrap")


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
        except PyMongoError as e:
            # No aborta el arranque; solo deja sin validator estricto.
            _log.warning("No se pudo aplicar validator en '%s': %s", name, e)


def _ensure_indexes(name: str, indexes: List[Dict[str, Any]]) -> None:
    coll = get_db()[name]
    for ix in indexes:
        keys = ix.pop("keys")
        try:
            coll.create_index(keys, **ix)
        except PyMongoError as e:
            # Ignora fallas de índice (e.g., ya existe o datos no únicos previos)
            _log.warning("No se pudo crear índice en '%s' (%s): %s", name, keys, e)


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

    # Refresh Tokens (rotación segura por familia)
    refresh_token_validator = {
        "bsonType": "object",
        "required": [
            "user_id",
            "token_hash",
            "family_id",
            "device_id",
            "ip",
            "user_agent",
            "created_at",
            "expires_at",
        ],
        "properties": {
            "user_id": {"bsonType": "objectId"},
            "token_hash": {"bsonType": "string"},
            "family_id": {"bsonType": "string"},
            "rotation_parent_id": {"bsonType": ["objectId", "null"]},
            "device_id": {"bsonType": "string"},
            "ip": {"bsonType": "string"},
            "user_agent": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
            "expires_at": {"bsonType": "date"},
            "revoked_at": {"bsonType": ["date", "null"]},
            "revoked_reason": {"bsonType": ["string", "null"]},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("refresh_token", refresh_token_validator)
    _ensure_indexes(
        "refresh_token",
        [
            {"keys": [("token_hash", 1)], "unique": True, "name": "uniq_token_hash"},
            {"keys": [("user_id", 1), ("expires_at", 1)], "name": "ix_user_expires"},
            {"keys": [("family_id", 1)], "name": "ix_family"},
        ],
    )

    # (Colección `materias` legacy deshabilitada: reemplazada por catálogos + timetable)

    # Horarios (para consultas por usuario + día + hora)
    # Día admite nombres comunes en español (corto/largo, con/sin acento) para compatibilidad
    # (Colección `horarios` legacy deshabilitada: reemplazada por timetable/timetable_entry)

    # (Colección `notas` eliminada en favor de `note`)

    # (Colección `consultas` eliminada: reemplazada por conversations/messages)

    # Academics: Catálogos
    department_validator = {
        "bsonType": "object",
        "required": ["code", "name", "created_at", "updated_at"],
        "properties": {
            "code": {"bsonType": "string"},
            "name": {"bsonType": "string"},
            "campus": {"bsonType": ["string", "null"]},
            "created_at": {"bsonType": "string", "minLength": 10},
            "updated_at": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("department", department_validator)
    _ensure_indexes("department", [{"keys": [("code", 1)], "unique": True, "name": "uniq_department_code"}])

    program_validator = {
        "bsonType": "object",
        "required": ["department_code", "code", "created_at", "updated_at"],
        "properties": {
            "department_code": {"bsonType": "string"},
            "code": {"bsonType": "string"},
            "name": {"bsonType": ["string", "null"]},
            "created_at": {"bsonType": "string", "minLength": 10},
            "updated_at": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("program", program_validator)
    _ensure_indexes("program", [{"keys": [("department_code", 1), ("code", 1)], "unique": True, "name": "uniq_program"}])

    period_validator = {
        "bsonType": "object",
        "required": ["code", "year", "term", "status", "created_at", "updated_at"],
        "properties": {
            "code": {"bsonType": "string"},
            "year": {"bsonType": "int"},
            "term": {"bsonType": "string"},
            "start_date": {"bsonType": ["string", "null"]},
            "end_date": {"bsonType": ["string", "null"]},
            "status": {"bsonType": "string", "enum": ["planned", "active", "archived"]},
            "created_at": {"bsonType": "string", "minLength": 10},
            "updated_at": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("period", period_validator)
    _ensure_indexes("period", [
        {"keys": [("code", 1)], "unique": True, "name": "uniq_period_code"},
        {"keys": [("status", 1)], "name": "ix_period_status"},
    ])

    course_validator = {
        "bsonType": "object",
        "required": ["name", "created_at", "updated_at"],
        "properties": {
            "code": {"bsonType": ["string", "null"]},
            "name": {"bsonType": "string"},
            "short_name": {"bsonType": ["string", "null"]},
            "credits": {"bsonType": ["int", "null"]},
            "created_at": {"bsonType": "string", "minLength": 10},
            "updated_at": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("course", course_validator)
    _ensure_indexes("course", [
        {"keys": [("code", 1)], "name": "ix_course_code", "unique": False},
        {"keys": [("name", 1)], "name": "ix_course_name"},
    ])

    # Academics: Timetables
    timetable_validator = {
        "bsonType": "object",
        "required": [
            "department_code",
            "program_code",
            "semester",
            "group",
            "period_code",
            "title",
            "status",
            "version",
            "is_current",
            "created_at",
            "updated_at",
        ],
        "properties": {
            "department_code": {"bsonType": "string"},
            "program_code": {"bsonType": "string"},
            "semester": {"bsonType": "int", "minimum": 1},
            "group": {"bsonType": "string"},
            "period_code": {"bsonType": "string"},
            "shift": {"bsonType": ["string", "null"], "enum": ["TM", "TV", None]},
            "title": {"bsonType": "string"},
            "status": {"bsonType": "string", "enum": ["draft", "published", "archived"]},
            "version": {"bsonType": "int", "minimum": 1},
            "is_current": {"bsonType": "bool"},
            "notes": {"bsonType": ["string", "null"]},
            "created_at": {"bsonType": "string", "minLength": 10},
            "updated_at": {"bsonType": "string", "minLength": 10},
            "published_at": {"bsonType": ["string", "null"]},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("timetable", timetable_validator)
    _ensure_indexes(
        "timetable",
        [
            {"keys": [("department_code", 1), ("program_code", 1), ("semester", 1), ("group", 1), ("period_code", 1), ("version", 1)], "name": "uniq_timetable_combo", "unique": True},
            {"keys": [("department_code", 1), ("program_code", 1), ("semester", 1), ("group", 1), ("period_code", 1), ("is_current", 1)], "name": "ix_current_combo"},
        ],
    )

    timetable_entry_validator = {
        "bsonType": "object",
        "required": [
            "timetable_id",
            "day",
            "start_time",
            "end_time",
            "course_name",
            "created_at",
            "updated_at",
        ],
        "properties": {
            "timetable_id": {"bsonType": "string"},
            "day": {"bsonType": "string", "enum": ["mon", "tue", "wed", "thu", "fri", "sat"]},
            "start_time": {"bsonType": "string", "pattern": "^\\d{2}:\\d{2}$"},
            "end_time": {"bsonType": "string", "pattern": "^\\d{2}:\\d{2}$"},
            "course_name": {"bsonType": "string"},
            "instructor": {"bsonType": ["string", "null"]},
            "room_code": {"bsonType": ["string", "null"]},
            "modality": {"bsonType": "string", "enum": ["class", "lab", "seminar", "other"]},
            "module": {"bsonType": ["string", "null"]},
            "notes": {"bsonType": ["string", "null"]},
            "created_at": {"bsonType": "string", "minLength": 10},
            "updated_at": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("timetable_entry", timetable_entry_validator)
    _ensure_indexes(
        "timetable_entry",
        [
            {"keys": [("timetable_id", 1), ("day", 1), ("start_time", 1)], "name": "ix_timetable_day_start"},
            {"keys": [("timetable_id", 1)], "name": "ix_timetable"},
        ],
    )

    # Conversations (chat)
    conversations_validator = {
        "bsonType": "object",
        "required": ["title", "status", "model", "last_message_at", "created_at", "updated_at"],
        "properties": {
            "user_id": {"bsonType": ["string", "null"]},
            "session_id": {"bsonType": ["string", "null"]},
            "mode": {"bsonType": ["string", "null"], "enum": ["auth", "guest", None]},
            "title": {"bsonType": "string"},
            "status": {"bsonType": "string", "enum": ["active", "archived"]},
            "model": {"bsonType": "string"},
            "settings": {"bsonType": ["object", "null"]},
            "metadata": {"bsonType": ["object", "null"]},
            "last_message_at": {"bsonType": "string", "minLength": 10},
            "created_at": {"bsonType": "string", "minLength": 10},
            "updated_at": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
        "anyOf": [
            {"required": ["user_id"]},
            {"required": ["session_id"]},
        ],
    }
    _collmod_or_create("conversations", conversations_validator)
    _ensure_indexes(
        "conversations",
        [
            {"keys": [("user_id", 1), ("updated_at", -1)], "name": "ix_conv_user_updated"},
            {"keys": [("user_id", 1), ("status", 1), ("updated_at", -1)], "name": "ix_conv_user_status"},
            {"keys": [("session_id", 1), ("updated_at", -1)], "name": "ix_conv_session_updated"},
        ],
    )

    # Messages (chat)
    messages_validator = {
        "bsonType": "object",
        "required": ["conversation_id", "role", "content", "created_at"],
        "properties": {
            "conversation_id": {"bsonType": "string", "minLength": 10},
            "user_id": {"bsonType": ["string", "null"]},
            "session_id": {"bsonType": ["string", "null"]},
            "role": {"bsonType": "string", "enum": ["user", "assistant", "system", "tool"]},
            "content": {"bsonType": "string"},
            "attachments": {"bsonType": "array", "items": {"bsonType": "string"}},
            "citations": {"bsonType": "array"},
            "model_snapshot": {"bsonType": ["string", "null"]},
            "tokens_input": {"bsonType": ["int", "null"]},
            "tokens_output": {"bsonType": ["int", "null"]},
            "error": {"bsonType": ["object", "null"]},
            "created_at": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
        "anyOf": [
            {"required": ["user_id"]},
            {"required": ["session_id"]},
        ],
    }
    _collmod_or_create("messages", messages_validator)
    _ensure_indexes(
        "messages",
        [
            {"keys": [("conversation_id", 1), ("created_at", 1)], "name": "ix_msg_conv_created"},
            {"keys": [("user_id", 1), ("created_at", -1)], "name": "ix_msg_user_created"},
            {"keys": [("session_id", 1), ("created_at", 1)], "name": "ix_msg_session_created"},
        ],
    )

    # Note (singular)
    note_validator = {
        "bsonType": "object",
        "required": [
            "user_id",
            "title",
            "body",
            "tags",
            "status",
            "source",
            "created_at",
            "updated_at",
        ],
        "properties": {
            "user_id": {"bsonType": "string", "minLength": 10},
            "title": {"bsonType": "string", "minLength": 1},
            "body": {"bsonType": "string", "minLength": 1},
            "tags": {"bsonType": "array", "items": {"bsonType": "string"}},
            "status": {"bsonType": "string", "enum": ["active", "archived"]},
            "source": {"bsonType": "string", "enum": ["manual", "assistant", "imported"]},
            "related_conversation_id": {"bsonType": ["string", "null"]},
            "created_at": {"bsonType": "string", "minLength": 10},
            "updated_at": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("note", note_validator)
    _ensure_indexes(
        "note",
        [
            {"keys": [("user_id", 1), ("updated_at", -1)], "name": "ix_note_user_updated"},
            {"keys": [("user_id", 1), ("status", 1), ("updated_at", -1)], "name": "ix_note_user_status"},
            {"keys": [("user_id", 1), ("tags", 1)], "name": "ix_note_user_tags"},
        ],
    )

    # Biblioteca de documentos institucionales (formularios, formatos, PDFs)
    library_doc_validator = {
        "bsonType": "object",
        "required": [
            "title",
            "status",
            "created_at",
            "updated_at",
        ],
        "properties": {
            "title": {"bsonType": "string"},
            "aliases": {"bsonType": "array", "items": {"bsonType": "string"}},
            "tags": {"bsonType": "array", "items": {"bsonType": "string"}},
            "department": {"bsonType": ["string", "null"]},
            "program": {"bsonType": ["string", "null"]},
            "campus": {"bsonType": ["string", "null"]},
            "status": {"bsonType": "string", "enum": ["active", "archived"]},
            # Almacenamiento (R2 / S3 compatible)
            "url": {"bsonType": ["string", "null"]},
            "content_type": {"bsonType": ["string", "null"]},
            "size": {"bsonType": ["int", "null"]},
            # Auditoría
            "created_at": {"bsonType": "string", "minLength": 10},
            "updated_at": {"bsonType": "string", "minLength": 10},
        },
        "additionalProperties": True,
    }
    _collmod_or_create("library_doc", library_doc_validator)
    _ensure_indexes(
        "library_doc",
        [
            {"keys": [("status", 1)], "name": "ix_lib_status"},
            # Búsqueda simple por campos comunes
            {"keys": [("title", "text"), ("aliases", "text"), ("tags", "text")], "name": "txt_lib_title_aliases_tags"},
        ],
    )
