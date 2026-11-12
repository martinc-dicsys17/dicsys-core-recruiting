"""
Módulo Recibos de Sueldo - Portal del empleado.
"""

from backend.core.registry import registrar_modulo

registrar_modulo(
    codigo="recibos",
    nombre="Mis Recibos",
    icono="file-text",
    orden=9,
    items=[
        {
            "codigo": "mis_recibos",
            "nombre": "Mis Recibos",
            "icono": "file-text",
            "ruta": "recibos_portal.mis_recibos",
            "orden": 1,
        },
    ],
)
