"""
Servicio simple de envío de correos (SMTP) y generación de tokens de verificación.
"""
import smtplib
from email.message import EmailMessage
from typing import Dict
from datetime import datetime, timedelta, timezone

from app.core.config import settings

# Reutilizamos PyJWT vía token_service para mantener una sola dependencia
from app.services.token_service import pyjwt as _jwt


def _now_utc():
    return datetime.now(timezone.utc)


def create_email_verification_token(user_id: str, expires_in_hours: int = 24) -> str:
    now = _now_utc()
    payload = {
        "sub": user_id,
        "purpose": "email_verify",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_in_hours)).timestamp()),
    }
    return _jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> None:
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_pass:
        raise RuntimeError("SMTP no configurado. Define SMTP_HOST/SMTP_USER/SMTP_PASS en .env")

    msg = EmailMessage()
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email or settings.smtp_user}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    if text_body:
        msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    # Conexión TLS por defecto (587)
    if settings.smtp_use_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.send_message(msg)
    else:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
            server.login(settings.smtp_user, settings.smtp_pass)
            server.send_message(msg)


def send_verification_email(user: Dict) -> str:
    """
    Genera token y envía correo de verificación. Devuelve el link usado.
    """
    user_id = str(user.get("_id"))
    email = user.get("email")
    token = create_email_verification_token(user_id)
    link = f"{settings.email_verify_link_base}{token}"

    subject = "Verifica tu correo en AURA"
    html = f"""
    <p>Hola,</p>
    <p>Gracias por registrarte en <b>AURA</b>. Para activar tu cuenta, por favor verifica tu correo haciendo clic en el siguiente botón:</p>
    <p><a href="{link}" style="display:inline-block;padding:10px 16px;background:#4f46e5;color:#fff;text-decoration:none;border-radius:6px">Verificar correo</a></p>
    <p>Si el botón no funciona, copia y pega este enlace en tu navegador:</p>
    <p><a href="{link}">{link}</a></p>
    <p>Este enlace expira en 24 horas.</p>
    <p>— Equipo AURA</p>
    """
    text = f"Verifica tu correo en AURA: {link}\nEste enlace expira en 24 horas."

    send_email(email, subject, html, text)
    return link

