"""
Módulo Innovación - Certificaciones, eventos y gestión de licencias.
"""

from backend.core.registry import registrar_modulo

registrar_modulo(
    codigo="innovacion",
    nombre="Innovación",
    icono="lightbulb",
    orden=7,
    items=[
        {"codigo": "resumen", "nombre": "Resumen", "icono": "bar-chart-3", "ruta": "innovacion.resumen", "orden": 1},
        {
            "codigo": "mi_path",
            "nombre": "Mi Path de Certificación",
            "icono": "route",
            "ruta": "innovacion.mi_path",
            "orden": 2,
        },
        {
            "codigo": "admin_certificaciones",
            "nombre": "Administración",
            "icono": "settings",
            "ruta": "innovacion.admin_list",
            "orden": 3,
        },
        {
            "codigo": "admin_eventos",
            "nombre": "Eventos",
            "icono": "calendar",
            "ruta": "innovacion.eventos_list",
            "orden": 4,
        },
        {
            "codigo": "licencias",
            "nombre": "Gestión de Licencias",
            "icono": "key",
            "ruta": "innovacion.licencias_list",
            "orden": 5,
        },
    ],
)
