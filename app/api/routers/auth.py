"""Rutas de autenticación: registro, login, verificación, refresh y logout."""
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
from app.repositories import auth_repo as repo

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar usuario",
    description="Valida payload y registra usuario (local/Google).",
)
def register(payload: RegisterPayload):
    try:
        res = service.register_user(payload)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/verify-email",
    response_model=dict,
    summary="Verificar email con código",
    description="Valida código OTP enviado por correo y marca el email como verificado.",
)
def verify_email_code(payload: VerifyEmailCodePayload):
    try:
        res = service.verify_email_code(verification_token=payload.verification_token, code=payload.code)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/verify-email",
    response_model=dict,
    summary="Verificar email con link",
    description="Usa token firmado para verificar email (flujo de link).",
)
def verify_email(token: str = Query(..., description="Token de verificación de email")):
    try:
        res = service.verify_email_link(token=token)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _client_info(request: Request):
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    return ip, ua


@router.post(
    "/login",
    response_model=dict,
    summary="Login (local o Google) con payload flexible",
    description="Detecta si es login local (email+password) o Google (email+google_id).",
)
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


@router.post(
    "/google",
    response_model=dict,
    summary="Login con Google ID Token",
    description="Verifica Google ID Token y emite tokens.",
)
def login_with_google_token(payload: GoogleIdTokenPayload, request: Request):
    try:
        ip, ua = _client_info(request)
        res = service.login_with_google_token(id_token=payload.id_token, device_id=payload.device_id, ip=ip, user_agent=ua)
        return res
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Google login falló: {e}")


@router.post(
    "/send-verification",
    response_model=dict,
    summary="Enviar verificación por correo",
    description="Envía código OTP por correo y devuelve token corto para verificación.",
)
def send_verification(payload: SendVerificationPayload):
    res = service.send_verification(payload)
    return res


@router.get(
    "/me",
    response_model=dict,
    summary="Perfil básico del usuario",
    description="Devuelve información básica del usuario autenticado.",
)
def me(user=Depends(get_current_user)):
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


@router.post(
    "/refresh",
    response_model=dict,
    summary="Rotar refresh token",
    description="Rota el refresh token y emite un nuevo access token.",
)
def refresh(payload: RefreshPayload, request: Request):
    try:
        ip, ua = _client_info(request)
        new_raw, _ = service.rotate_refresh_token(current_raw=payload.refresh_token, device_id=payload.device_id, ip=ip, user_agent=ua)
        # Emitir nuevo access token para el mismo usuario de ese refresh
        # Recupera el RT actual para obtener user_id
        from app.repositories.auth_repo import get_refresh_token_by_hash
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


@router.post(
    "/logout",
    response_model=dict,
    summary="Cerrar sesión",
    description="Revoca el refresh token actual.",
)
def logout(payload: LogoutPayload):
    service.logout_refresh_token(current_raw=payload.refresh_token)
    return {"message": "ok"}


@router.post(
    "/force-logout",
    response_model=dict,
    summary="Forzar logout de un usuario",
    description="Revoca sesiones (incrementa token_version). Requiere ser el mismo usuario.",
)
def force_logout(payload: ForceLogoutPayload, user=Depends(get_current_user)):
    # Requiere ser el mismo usuario o un admin (simplificado)
    if str(user["_id"]) != payload.user_id:
        raise HTTPException(status_code=403, detail="No autorizado")
    service.force_logout_all(user_id=payload.user_id)
    return {"message": "ok"}
