"""
Módulo Star Miles - Sistema de millas para empleados.
"""

from backend.core.registry import registrar_modulo

registrar_modulo(
    codigo="starmiles",
    nombre="Star Miles",
    icono="star",
    orden=3,
    items=[
        {"codigo": "home", "nombre": "Portal", "icono": "home", "ruta": "starmiles.home", "orden": 1},
        {
            "codigo": "aprobar_inscripciones",
            "nombre": "Aprobar Inscripciones",
            "icono": "clipboard-check",
            "ruta": "starmiles.aprobador_inscripciones",
            "orden": 2,
        },
        {
            "codigo": "aprobar_canjes",
            "nombre": "Aprobar Canjes",
            "icono": "package-check",
            "ruta": "starmiles.aprobador_canjes",
            "orden": 3,
        },
        {
            "codigo": "admin_empleados",
            "nombre": "Gestionar Empleados",
            "icono": "users",
            "ruta": "starmiles.admin_empleados",
            "orden": 4,
        },
        {
            "codigo": "admin_desafios",
            "nombre": "Gestionar Desafíos",
            "icono": "settings",
            "ruta": "starmiles.admin_desafios",
            "orden": 5,
        },
        {
            "codigo": "admin_canjes",
            "nombre": "Gestionar Canjes",
            "icono": "box",
            "ruta": "starmiles.admin_items_canje",
            "orden": 6,
        },
        {
            "codigo": "admin_categorias",
            "nombre": "Gestionar Categorías",
            "icono": "tag",
            "ruta": "starmiles.admin_categorias",
            "orden": 7,
        },
        {
            "codigo": "admin_cms",
            "nombre": "Gestionar Contenido",
            "icono": "file-text",
            "ruta": "starmiles.admin_cms",
            "orden": 8,
        },
    ],
)
