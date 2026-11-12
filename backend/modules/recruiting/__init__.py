"""Módulo de Recruiting: sus modelos (tablas y catálogos de la revisión 0006) y su entrada en el menú.

El módulo se registra en el registry (fuente de verdad del sidebar y de los permisos): los permisos que se asignan
a los grupos son 'recruiting' y 'recruiting.<codigo>' de cada ítem. Las pantallas se migran de a una.

'ruta' es el endpoint del blueprint 'recruiting' del frontend (frontend/modulos/recruiting). El sidebar lo resuelve con
url_for, que fallaría para todos los usuarios con un endpoint inexistente: un ítem lleva su ruta recién cuando su
pantalla existe. Hasta entonces va con ruta=None y se muestra como "Próx." (igual que los pendientes de Nómina). Los
endpoints que faltan son los del módulo original: recruiting.candidatos, recruiting.oportunidades,
recruiting.gestion_busquedas y recruiting.parametros.
"""

from backend.core.registry import registrar_modulo

registrar_modulo(
    codigo="recruiting",
    nombre="Recruiting",
    icono="user-check",
    orden=0,
    items=[
        {
            "codigo": "dashboard",
            "nombre": "Dashboard Recruiting",
            "icono": "layout-dashboard",
            "ruta": "recruiting.dashboard",
            "orden": 0,
        },
        {
            "codigo": "candidatos",
            "nombre": "Candidatos",
            "icono": "users",
            "ruta": None,
            "orden": 1,
        },
        {
            "codigo": "oportunidades",
            "nombre": "Búsquedas",
            "icono": "list",
            "ruta": None,
            "orden": 2,
        },
        {
            "codigo": "gestion_busquedas",
            "nombre": "Pipeline",
            "icono": "layers",
            "ruta": None,
            "orden": 3,
        },
        {
            "codigo": "parametros",
            "nombre": "Parámetros",
            "icono": "sliders-horizontal",
            "ruta": None,
            "orden": 4,
        },
    ],
)
