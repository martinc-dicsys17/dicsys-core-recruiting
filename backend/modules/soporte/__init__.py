"""Módulo de Soporte Técnico."""

from backend.core.registry import registrar_modulo

registrar_modulo(
    codigo="soporte",
    nombre="Soporte IT",
    icono="headset",
    orden=7,
    items=[
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
        {"codigo": "stock_list", "nombre": "Stock IT", "icono": "package", "ruta": "soporte.stock_list", "orden": 3},
        {
            "codigo": "mis_solicitudes",
            "nombre": "Mis Solicitudes",
            "icono": "user-check",
            "ruta": "soporte.mis_solicitudes",
            "orden": 4,
        },
    ],
)
