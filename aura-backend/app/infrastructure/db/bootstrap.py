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

    # (Colección `notas` eliminada en favor de `note`)

    # (Colección `consultas` eliminada: reemplazada por conversations/messages)

    # Conversations (chat)
    conversations_validator = {
        "bsonType": "object",
        "required": [
            "user_id",
            "title",
            "status",
            "model",
            "last_message_at",
            "created_at",
            "updated_at",
        ],
        "properties": {
            "user_id": {"bsonType": "string", "minLength": 10},
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
    }
    _collmod_or_create("conversations", conversations_validator)
    _ensure_indexes(
        "conversations",
        [
            {"keys": [("user_id", 1), ("updated_at", -1)], "name": "ix_conv_user_updated"},
            {"keys": [("user_id", 1), ("status", 1), ("updated_at", -1)], "name": "ix_conv_user_status"},
        ],
    )

    # Messages (chat)
    messages_validator = {
        "bsonType": "object",
        "required": ["conversation_id", "user_id", "role", "content", "created_at"],
        "properties": {
            "conversation_id": {"bsonType": "string", "minLength": 10},
            "user_id": {"bsonType": "string", "minLength": 10},
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
    }
    _collmod_or_create("messages", messages_validator)
    _ensure_indexes(
        "messages",
        [
            {"keys": [("conversation_id", 1), ("created_at", 1)], "name": "ix_msg_conv_created"},
            {"keys": [("user_id", 1), ("created_at", -1)], "name": "ix_msg_user_created"},
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
