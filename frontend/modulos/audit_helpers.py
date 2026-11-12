"""
Helper centralizado de auditoría para el frontend.
Registra navegaciones efectivas (accesos concedidos) en el backend.
"""

import logging

import httpx
from flask import current_app, request, session

logger = logging.getLogger(__name__)


def registrar_auditoria(modulo: str, ruta: str = None, metodo: str = None, email: str = None):
    """
    Registra un acceso efectivo en el backend de auditoría.

    Parámetros:
        modulo: slug del módulo (ej: 'administracion/recibos')
        ruta: path completo (default: request.path)
        metodo: HTTP method (default: request.method)
        email: email del usuario (default: session user email)

    Solo registra si hay token y empresa activa en sesión.
    Fire-and-forget: no lanza excepciones si falla.
    """
    token = session.get("token")
    if not token:
        return

    if not session.get("empresa_id"):
        return

    if ruta is None:
        ruta = request.path or "/"
    if metodo is None:
        metodo = request.method
    if email is None:
        user = session.get("user", {})
        email = user.get("email", "")

    try:
        url = f"{current_app.config['API_URL']}/api/v1/auditoria"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        payload = {
            "modulo": modulo,
            "ruta": ruta,
            "metodo": metodo,
            "email_usuario": email,
        }
        with httpx.Client(timeout=5.0) as client:
            client.post(url, json=payload, headers=headers)
    except Exception as e:
        logger.warning(f"[AUDIT] Error al registrar navegación: {e}")
