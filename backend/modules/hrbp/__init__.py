# Módulo HRBP - Gestión de Entregas RRHH
from backend.core.registry import registrar_modulo

registrar_modulo(
    codigo="hrbp",
    nombre="HRBP",
    icono="heart-handshake",
    orden=4,
    items=[
        {
            "codigo": "gestion_items",
            "nombre": "Gestión de Items",
            "icono": "package",
            "ruta": "hrbp.items_list",
            "orden": 1,
        },
        {
            "codigo": "entregas",
            "nombre": "Gestión de Entregas",
            "icono": "gift",
            "ruta": "hrbp.entregas_list",
            "orden": 2,
        },
    ],
)
