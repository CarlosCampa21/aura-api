"""
Servicio simple de envío de correos (SMTP), generación de tokens y códigos de verificación.
"""
import smtplib
from email.message import EmailMessage
from typing import Dict
from datetime import datetime, timedelta, timezone
import secrets
import string

from app.core.config import settings

# Reutilizamos PyJWT vía token_service para mantener una sola dependencia
from app.infrastructure.security.token_service import pyjwt as _jwt


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


def generate_numeric_code(length: int = 6) -> str:
    alphabet = string.digits
    # Garantiza que el primer dígito no sea 0 para mejor UX
    first = secrets.choice("123456789")
    rest = "".join(secrets.choice(alphabet) for _ in range(max(0, length - 1)))
    return first + rest


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
    link = settings.email_verify_link(token)

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


def send_verification_code_email(user: Dict, code: str, expires_in_minutes: int) -> None:
    email = user.get("email")
    subject = "Tu código de verificación de AURA"
    html = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f7f8;padding:24px 0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif;color:#111">
      <tr>
        <td align="center">
          <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;border:1px solid #e6e6e7;padding:24px">
            <tr><td>
              <h2 style="margin:0 0 8px;font-size:20px;color:#111">Verifica tu correo en AURA</h2>
              <p style="margin:0 0 16px;color:#444">Usa este código para verificar tu correo electrónico:</p>
              <div style="display:inline-block;font-size:28px;letter-spacing:4px;font-weight:700;background:#111;color:#fff;padding:12px 16px;border-radius:8px">{code}</div>
              <p style="margin:16px 0 0;color:#555">Este código expira en <b>{expires_in_minutes} minutos</b>. Si no intentaste registrarte o iniciar sesión, puedes ignorar este mensaje.</p>
              <p style="margin:12px 0 0;color:#888">— Equipo AURA</p>
            </td></tr>
          </table>
        </td>
      </tr>
    </table>
    """
    text = f"Tu código de verificación de AURA es: {code}. Expira en {expires_in_minutes} minutos."
    send_email(email, subject, html, text)
