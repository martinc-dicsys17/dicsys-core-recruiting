"""
Módulo core de la aplicación.
"""

from backend.core.email import EmailSchema, EmailService, email_service, init_email_service
from backend.core.webex import WebexMessage, WebexService, build_notification_card, init_webex_service, webex_service

__all__ = [
    "email_service",
    "EmailSchema",
    "EmailService",
    "init_email_service",
    "webex_service",
    "WebexMessage",
    "WebexService",
    "init_webex_service",
    "build_notification_card",
]
