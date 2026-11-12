"""
Módulo de envío de correos electrónicos usando SendGrid.
"""

import logging
from typing import List, Optional, Union

from fastapi import HTTPException
from pydantic import BaseModel
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Content, Email, Mail, To

from backend.core.adapter_proxy import AdapterProxy
from backend.core.config import settings

logger = logging.getLogger(__name__)


class EmailSchema(BaseModel):
    """Esquema para envío de correos."""

    to: Union[str, List[str]]
    subject: str
    html: str
    from_email: Optional[str] = None
    reply_to: Optional[str] = None


class EmailService:
    """Servicio para envío de correos electrónicos con SendGrid."""

    def __init__(self):
        self._api_key: Optional[str] = None
        self._client: Optional[SendGridAPIClient] = None
        self._default_from: str = "noreply@example.com"

    def configure(self, api_key: str, default_from: Optional[str] = None):
        """
        Configura el servicio de email.

        Args:
            api_key: API key de SendGrid
            default_from: Email remitente por defecto
        """
        self._api_key = api_key
        self._client = SendGridAPIClient(api_key)
        if default_from:
            self._default_from = default_from

    def _ensure_configured(self):
        """Verifica que el servicio esté configurado."""
        if not self._api_key or not self._client:
            logger.error("❌ Email service no configurado - falta API key")
            raise HTTPException(status_code=500, detail="El servicio de email no está configurado")

    def send(
        self,
        to: Union[str, List[str]],
        subject: str,
        html: str,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> dict:
        """
        Envía un correo electrónico.

        Args:
            to: Destinatario(s) del correo
            subject: Asunto del correo
            html: Contenido HTML del correo
            from_email: Email remitente (opcional, usa default si no se especifica)
            reply_to: Email para respuestas (opcional)

        Returns:
            dict: Respuesta de SendGrid con status code y message_id

        Raises:
            HTTPException: Si hay error en el envío
        """
        self._ensure_configured()

        try:
            sender = from_email or self._default_from
            recipients = to if isinstance(to, list) else [to]

            logger.info(f"📧 Enviando email a: {recipients}, subject: {subject}")
            logger.debug(f"📧 From: {sender}")

            message = Mail(
                from_email=Email(sender),
                to_emails=[To(r) for r in recipients],
                subject=subject,
                html_content=Content("text/html", html),
            )

            if reply_to:
                message.reply_to = Email(reply_to)

            response = self._client.send(message)

            result = {"status_code": response.status_code, "message_id": response.headers.get("X-Message-Id", "")}

            logger.info(f"✅ Email enviado exitosamente. Status: {response.status_code}")
            return result

        except Exception as e:
            logger.error(f"❌ Error enviando email: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error al enviar correo: {str(e)}")

    def send_from_schema(self, email: EmailSchema) -> dict:
        """
        Envía un correo usando un esquema EmailSchema.

        Args:
            email: Esquema con los datos del correo

        Returns:
            dict: Respuesta de SendGrid
        """
        return self.send(
            to=email.to, subject=email.subject, html=email.html, from_email=email.from_email, reply_to=email.reply_to
        )


# Fachada estable: los callers conservan la referencia y tests cambian el adaptador.
email_service = AdapterProxy(EmailService())


def init_email_service():
    """
    Inicializa el servicio de email con la configuración de la aplicación.
    Llamar esta función al iniciar la aplicación.
    """
    if hasattr(settings, "sendgrid_api_key") and settings.sendgrid_api_key:
        default_from = getattr(settings, "email_from", None)
        email_service.configure(settings.sendgrid_api_key, default_from)
        logger.info(f"✅ Email service configurado con SendGrid. From: {default_from or 'noreply@example.com'}")
    else:
        logger.warning("⚠️ SENDGRID_API_KEY no configurada - emails deshabilitados")
