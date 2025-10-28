"""
Rutas de autenticación para AURA.
"""
from fastapi import APIRouter, HTTPException, status, Request, Depends, Query
 

# Capa de dominio: esquemas de autenticación (valores y validaciones)
from app.api.schemas.auth import (
    RegisterPayload,
    UserRegisterInput,
    VerifyEmailCodePayload,
    LoginLocalPayload,
    LoginGooglePayload,
    GoogleIdTokenPayload,
    SendVerificationPayload,
    RefreshPayload,
    LogoutPayload,
    ForceLogoutPayload,
)

# Servicios: lógica de negocio (hashing, tokens, repos, correo)
from app.services import auth_service as service
from app.api.deps import get_current_user
from app.core import rate_limit
from app.repositories import auth_repository as repo
# Nota: token_service se usa dentro de los servicios; la API no lo necesita directamente.


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterPayload):
    """
    Registro de usuarios.

    - La validación y normalización del payload viven en `app.api.schemas.auth`.
    - La lógica (hash, insertar, correo, token de verificación) vive en `app.services.auth_service`.
    """
    try:
        return service.register_user(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registro falló: {e}")


@router.post("/verify-email", response_model=dict)
def verify_email_code(payload: VerifyEmailCodePayload):
    """Verifica el email comparando un OTP con su hash almacenado."""
    try:
        return service.verify_email_code(verification_token=payload.verification_token, code=payload.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo verificar email: {e}")


@router.get("/verify-email", response_model=dict)
def verify_email(token: str = Query(..., description="Token de verificación de email")):
    """Verifica email usando un token firmado (recomendado)."""
    try:
        return service.verify_email_link(token=token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token inválido: {e}")


def _client_info(request: Request):
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    return ip, ua


@router.post("/login", response_model=dict)
def login(payload: dict, request: Request):
    try:
        # Rate limit por IP
        ip = request.client.host if request.client else ""
        if not rate_limit.allow((ip, "/auth/login")):
            raise HTTPException(status_code=429, detail="Demasiados intentos, espera un momento")
        ip, ua = _client_info(request)
        if "password" in payload:
            lp = LoginLocalPayload(**payload)
            tokens = service.login_local(email=str(lp.email).lower(), password=lp.password, device_id=lp.device_id, ip=ip, user_agent=ua)
            return tokens
        elif "google_id" in payload and "email" in payload:
            # Compatibilidad: login Google con email + google_id (sin verificar id_token)
            gp = LoginGooglePayload(**payload)
            tokens = service.login_google(email=str(gp.email).lower(), google_id=gp.google_id, device_id=gp.device_id, ip=ip, user_agent=ua)
            return tokens
        else:
            raise HTTPException(status_code=400, detail="Payload inválido")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Login inválido: {e}")


@router.post("/google", response_model=dict)
def login_with_google_token(payload: GoogleIdTokenPayload, request: Request):
    """Login con ID Token de Google (verificado por el servicio)."""
    try:
        ip, ua = _client_info(request)
        return service.login_with_google_token(id_token=payload.id_token, device_id=payload.device_id, ip=ip, user_agent=ua)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Google login falló: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Google login falló: {e}")


@router.post("/send-verification", response_model=dict)
def send_verification(payload: SendVerificationPayload):
    """Envía código de verificación por correo con expiración corta."""
    try:
        return service.send_verification(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo enviar verificación: {e}")


@router.get("/me", response_model=dict)
def me(user=Depends(get_current_user)):
    """
    Devuelve información básica del usuario autenticado.
    """
    try:
        # Filtra campos sensibles
        out = {
            "id": str(user.get("_id")),
            "email": user.get("email"),
            "auth_provider": user.get("auth_provider"),
            "email_verified": bool(user.get("email_verified")),
            "is_active": bool(user.get("is_active")),
            "profile": user.get("profile") or {},
        }
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo obtener perfil: {e}")


@router.post("/refresh", response_model=dict)
def refresh(payload: RefreshPayload, request: Request):
    try:
        ip, ua = _client_info(request)
        new_raw, _ = service.rotate_refresh_token(current_raw=payload.refresh_token, device_id=payload.device_id, ip=ip, user_agent=ua)
        # Emitir nuevo access token para el mismo usuario de ese refresh
        # Recupera el RT actual para obtener user_id
        from app.repositories.auth_repository import get_refresh_token_by_hash
        import hashlib

        cur = get_refresh_token_by_hash(hashlib.sha256(payload.refresh_token.encode("utf-8")).hexdigest())
        if not cur:
            raise HTTPException(status_code=401, detail="Refresh inválido")
        user = repo.get_user_by_id(str(cur["user_id"]))
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")
        access = service.create_access_token(user=user)
        return {"access_token": access, "refresh_token": new_raw}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Refresh inválido: {e}")


@router.post("/logout", response_model=dict)
def logout(payload: LogoutPayload):
    try:
        service.logout_refresh_token(current_raw=payload.refresh_token)
        return {"message": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Logout falló: {e}")


@router.post("/force-logout", response_model=dict)
def force_logout(payload: ForceLogoutPayload, user=Depends(get_current_user)):
    try:
        # Requiere ser el mismo usuario o un admin (aquí simplificado)
        if str(user["_id"]) != payload.user_id:
            raise HTTPException(status_code=403, detail="No autorizado")
        service.force_logout_all(user_id=payload.user_id)
        return {"message": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Force logout falló: {e}")
