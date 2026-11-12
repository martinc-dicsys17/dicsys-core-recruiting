"""
Módulo Soporte Técnico - Panel para usuarios de soporte
"""

from .app_module import soporte_bp


def registrar_modulo():
    """Registra el módulo de Soporte con su configuración."""
    return {
        "codigo": "soporte",
        "nombre": "Soporte IT",
        "icono": "headset",
        "orden": 7,
        "blueprint": soporte_bp,
        "items": [
            {
                "codigo": "dashboard",
                "nombre": "Dashboard",
                "icono": "layout-dashboard",
                "ruta": "soporte.dashboard",
                "orden": 1,
            },
            {
                "codigo": "tickets_kanban",
                "nombre": "Tickets",
                "icono": "ticket",
                "ruta": "soporte.tickets_kanban",
                "orden": 2,
            },
            {
                "codigo": "stock_list",
                "nombre": "Stock IT",
                "icono": "package",
                "ruta": "soporte.stock_list",
                "orden": 3,
            },
            {
                "codigo": "mis_solicitudes",
                "nombre": "Mis Solicitudes",
                "icono": "user-check",
                "ruta": "soporte.mis_solicitudes",
                "orden": 4,
            },
        ],
    }
