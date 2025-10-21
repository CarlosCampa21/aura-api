"""
Rutas de autenticación para AURA.
"""
from fastapi import APIRouter, HTTPException, status, Request, Depends
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional, Literal

from app.repositories import auth_repository as repo
from app.services import auth_service as service
from app.services.auth_validator import get_current_user
from app.services import rate_limit
from app.repositories.user_repo import insert_user


router = APIRouter(prefix="/auth", tags=["Auth"])


class UserRegisterInput(BaseModel):
    email: EmailStr
    auth_provider: Literal["local", "google"]
    google_id: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: EmailStr) -> str:
        return str(v).lower()

    @model_validator(mode="after")
    def _check_google(self):
        if self.auth_provider == "google" and not self.google_id:
            raise ValueError("google_id requerido para auth_provider=google")
        return self


class RegisterPayload(BaseModel):
    # Para local: password obligatorio. Para google: google_id obligatorio dentro de user
    user: UserRegisterInput
    password: Optional[str] = None


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterPayload):
    try:
        u = payload.user.model_dump()
        # Normaliza flags al crear
        u.setdefault("is_active", False)
        u.setdefault("email_verified", False)
        # Si local, almacenar password_hash
        if u.get("auth_provider") == "local":
            if not payload.password:
                raise HTTPException(status_code=400, detail="password requerido para local")
            u["password_hash"] = service.hash_password(payload.password)
        inserted_id = insert_user(u)
        return {"message": "ok", "id": inserted_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registro falló: {e}")


class VerifyEmailPayload(BaseModel):
    user_id: str


@router.post("/verify-email", response_model=dict)
def verify_email(payload: VerifyEmailPayload):
    try:
        repo.set_email_verified(payload.user_id)
        return {"message": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo verificar email: {e}")


class LoginLocalPayload(BaseModel):
    email: EmailStr
    password: str
    device_id: str


class LoginGooglePayload(BaseModel):
    email: EmailStr
    google_id: str
    device_id: str


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
        else:
            gp = LoginGooglePayload(**payload)
            tokens = service.login_google(email=str(gp.email).lower(), google_id=gp.google_id, device_id=gp.device_id, ip=ip, user_agent=ua)
            return tokens
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Login inválido: {e}")


class RefreshPayload(BaseModel):
    refresh_token: str
    device_id: str


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


class LogoutPayload(BaseModel):
    refresh_token: str


@router.post("/logout", response_model=dict)
def logout(payload: LogoutPayload):
    try:
        service.logout_refresh_token(current_raw=payload.refresh_token)
        return {"message": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Logout falló: {e}")


class ForceLogoutPayload(BaseModel):
    user_id: str


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
