"""
Lógica de autenticación: registro, login, refresh, logout, force-logout.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
import secrets
import hashlib

from argon2 import PasswordHasher
from argon2.low_level import Type

from app.core.config import settings
from app.repositories import auth_repository as repo
from app.services.token_service import create_access_token

# Nuevos imports para casos de uso de registro/verificación
from app.repositories.user_repo import insert_user
from app.services import email_service, token_service, google_oauth

# Esquemas de la capa de dominio (auth)
from app.domain.auth.schemas import (
    RegisterPayload,
    SendVerificationPayload,
)


ph = PasswordHasher(time_cost=2, memory_cost=51200, parallelism=2, hash_len=32, salt_len=16, type=Type.ID)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _refresh_token_exp() -> datetime:
    return _now_utc() + timedelta(days=settings.refresh_token_expire_days)


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except Exception:
        return False


def generate_refresh_token() -> str:
    # 256-bit random token in hex
    return secrets.token_hex(32)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_for_user(
    *, user_id: str, device_id: str, ip: str, user_agent: str, family_id: Optional[str] = None, rotation_parent_id: Optional[str] = None
) -> Tuple[str, str]:
    """
    Crea un refresh token (raw) y guarda su hash. Devuelve (raw_token, refresh_id).
    """
    raw = generate_refresh_token()
    doc = repo.create_refresh_token_doc(
        user_id=user_id,
        raw_token=raw,
        family_id=family_id,
        rotation_parent_id=rotation_parent_id,
        device_id=device_id,
        ip=ip,
        user_agent=user_agent,
        created_at=_now_utc(),
        expires_at=_refresh_token_exp(),
    )
    refresh_id = repo.insert_refresh_token(doc)
    return raw, refresh_id


def rotate_refresh_token(*, current_raw: str, device_id: str, ip: str, user_agent: str) -> Tuple[str, str]:
    """
    Valida el refresh actual (hash), lo revoca y crea uno nuevo de la misma familia.
    Devuelve (new_raw, new_refresh_id).
    """
    current = repo.get_refresh_token_by_hash(_hash(current_raw))
    if not current:
        raise ValueError("Refresh token desconocido")
    if current.get("revoked_at") is not None:
        raise ValueError("Refresh token revocado")
    if current.get("expires_at") <= _now_utc():
        raise ValueError("Refresh token expirado")

    repo.revoke_refresh_token(str(current["_id"]), reason="rotated")

    new_raw, new_id = create_refresh_for_user(
        user_id=str(current["user_id"]),
        device_id=device_id,
        ip=ip,
        user_agent=user_agent,
        family_id=current["family_id"],
        rotation_parent_id=str(current["_id"]),
    )
    return new_raw, new_id


def logout_refresh_token(*, current_raw: str) -> None:
    current = repo.get_refresh_token_by_hash(_hash(current_raw))
    if current:
        repo.revoke_refresh_token(str(current["_id"]), reason="logout")


def login_local(*, email: str, password: str, device_id: str, ip: str, user_agent: str) -> Dict[str, Any]:
    u = repo.find_user_by_email(email.lower())
    if not u or u.get("auth_provider") != "local":
        raise ValueError("Credenciales inválidas")
    if not u.get("password_hash") or not verify_password(password, u.get("password_hash")):
        raise ValueError("Credenciales inválidas")

    access = create_access_token(user=u)
    refresh_raw, _ = create_refresh_for_user(
        user_id=str(u["_id"]), device_id=device_id, ip=ip, user_agent=user_agent
    )
    return {"access_token": access, "refresh_token": refresh_raw}


def login_google(*, google_id: str, email: str, device_id: str, ip: str, user_agent: str) -> Dict[str, Any]:
    u = repo.find_user_by_email(email.lower())
    if not u or u.get("auth_provider") != "google" or u.get("google_id") != google_id:
        raise ValueError("Credenciales inválidas")
    access = create_access_token(user=u)
    refresh_raw, _ = create_refresh_for_user(
        user_id=str(u["_id"]), device_id=device_id, ip=ip, user_agent=user_agent
    )
    return {"access_token": access, "refresh_token": refresh_raw}


def force_logout_all(*, user_id: str) -> None:
    repo.increment_token_version(user_id)
    # Opcional: revocar familia(s) activas del usuario


# === Casos de uso de autenticación de más alto nivel ===

def register_user(payload: RegisterPayload) -> Dict[str, Any]:
    """
    Registra un usuario local o de Google.

    - Para `local`, genera y almacena `password_hash` y envía código de verificación por correo.
    - Para `google`, crea el usuario marcado como activo (la verificación viene por Google).
    """
    u = payload.user.model_dump()

    # Normaliza flags al crear
    u.setdefault("is_active", False)
    u.setdefault("email_verified", False)

    # Si local, almacenar password_hash
    if u.get("auth_provider") == "local":
        if not payload.password:
            raise ValueError("password requerido para local")
        u["password_hash"] = hash_password(payload.password)

    inserted_id = insert_user(u)

    # Si es local, genera código OTP + sesión de verificación y envía correo
    if u.get("auth_provider") == "local":
        user_doc = repo.get_user_by_id(inserted_id)
        try:
            from datetime import datetime, timedelta, timezone
            import hashlib

            code = email_service.generate_numeric_code(6)
            code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
            minutes = settings.email_code_expire_minutes
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            repo.set_email_verification_code(inserted_id, code_hash, expires_at)
            email_service.send_verification_code_email(user_doc, code, minutes)
            vtoken = token_service.create_email_code_token(user_id=inserted_id, expires_in_minutes=minutes)
            return {"message": "ok", "id": inserted_id, "verification_token": vtoken, "expires_in_minutes": minutes}
        except Exception as ex:
            # No abortar el registro por fallo de correo
            vtoken = token_service.create_email_code_token(user_id=inserted_id)
            return {"message": "ok", "id": inserted_id, "verification_token": vtoken, "email_notice": f"No se pudo enviar verificación: {ex}"}

    return {"message": "ok", "id": inserted_id}


def verify_email_code(*, verification_token: str, code: str) -> Dict[str, Any]:
    """
    Verificación por código (OTP) enviado por correo. Expira en minutos.
    """
    # Deriva user_id del token de verificación corto
    t = token_service.verify_email_code_token(verification_token)
    user_id = t.get("sub")
    u = repo.get_user_by_id(user_id)
    if not u:
        raise ValueError("Usuario no encontrado")

    # Si ya está verificado, no exigir código
    if u.get("email_verified"):
        return {"message": "ok", "already_verified": True}

    stored_hash = u.get("email_verify_code_hash")
    expires_at = u.get("email_verify_code_expires_at")
    if not stored_hash or not expires_at:
        raise ValueError("No hay código activo")

    import hashlib
    code_hash = hashlib.sha256(code.strip().encode("utf-8")).hexdigest()

    # Manejar expires_at como naive/aware
    from datetime import datetime, timezone
    if isinstance(expires_at, str):
        try:
            expires_dt = datetime.fromisoformat(expires_at)
        except Exception:
            expires_dt = datetime.now(timezone.utc)
    else:
        expires_dt = expires_at

    if expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires_dt:
        raise ValueError("Código expirado")

    if code_hash != stored_hash:
        raise ValueError("Código inválido")

    repo.set_email_verified(user_id)
    repo.clear_email_verification_code(user_id)
    return {"message": "ok"}


def verify_email_link(*, token: str) -> Dict[str, Any]:
    """
    Verifica email usando un token firmado (invocado desde link en correo).
    """
    from app.services.token_service import pyjwt as _jwt
    payload = _jwt.decode(token, key=settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose") != "email_verify":
        raise ValueError("Token inválido")
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Token inválido")
    repo.set_email_verified(user_id)
    return {"message": "ok"}


def send_verification(payload: SendVerificationPayload) -> Dict[str, Any]:
    """
    Envía código de verificación por correo con expiración corta.
    Si el usuario ya está verificado o no existe, responde 200 evitando revelar información.
    """
    from datetime import datetime, timedelta, timezone
    import hashlib

    u = None
    if payload.verification_token:
        try:
            t = token_service.verify_email_code_token(payload.verification_token)
            uid = t.get("sub")
            u = repo.get_user_by_id(uid)
        except Exception:
            u = None
    elif payload.email:
        u = repo.find_user_by_email(str(payload.email).lower())

    if u and u.get("email_verified"):
        return {"message": "ok", "already_verified": True}

    if not u:
        return {"message": "ok"}

    code = email_service.generate_numeric_code(6)
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    minutes = settings.email_code_expire_minutes
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    repo.set_email_verification_code(str(u["_id"]), code_hash, expires_at)
    email_service.send_verification_code_email(u, code, minutes)
    vtoken = token_service.create_email_code_token(user_id=str(u["_id"]), expires_in_minutes=minutes)
    return {"message": "ok", "expires_in_minutes": minutes, "verification_token": vtoken}


def login_with_google_token(*, id_token: str, device_id: str, ip: str, user_agent: str) -> Dict[str, Any]:
    """
    Verifica el ID Token de Google, crea el usuario si no existe y emite tokens.
    """
    claims = google_oauth.verify_id_token(id_token)
    email = str(claims.get("email", "")).lower()
    sub = claims.get("sub")  # google_id
    email_verified = bool(claims.get("email_verified", False))

    if not email or not sub:
        raise ValueError("Token de Google incompleto")

    u = repo.find_user_by_email(email)
    if not u:
        # auto-provisión
        inserted_id = insert_user(
            {
                "email": email,
                "auth_provider": "google",
                "google_id": sub,
                "is_active": True,
                "email_verified": email_verified,
            }
        )
        u = repo.get_user_by_id(inserted_id)
    else:
        if u.get("auth_provider") != "google" or u.get("google_id") != sub:
            raise ValueError("Cuenta existente con otro método de login")

    access = create_access_token(user=u)
    refresh_raw, _ = create_refresh_for_user(user_id=str(u["_id"]), device_id=device_id, ip=ip, user_agent=user_agent)
    return {"access_token": access, "refresh_token": refresh_raw}
