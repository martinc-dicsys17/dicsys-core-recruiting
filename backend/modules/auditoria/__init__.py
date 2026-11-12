"""
Módulo de Auditoría — registro de navegación de usuarios.
"""

from backend.core.registry import registrar_modulo

registrar_modulo(
    codigo="auditoria",
    nombre="Auditoría",
    icono="history",
    orden=10,
    items=[
        {
            "codigo": "log_navegacion",
            "nombre": "Log de Navegación",
            "icono": "history",
            "ruta": "administracion.auditoria_list",
            "orden": 1,
        },
    ],
)
