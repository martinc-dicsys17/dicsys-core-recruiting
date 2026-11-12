"""
Módulo de Operaciones - Gestión de equipos de trabajo.
"""

from backend.core.registry import registrar_modulo

registrar_modulo(
    codigo="operaciones",
    nombre="Operaciones",
    icono="briefcase",
    orden=6,
    items=[
        {"codigo": "equipos", "nombre": "Equipos", "icono": "users", "ruta": "operaciones.equipos_list", "orden": 1},
    ],
)
