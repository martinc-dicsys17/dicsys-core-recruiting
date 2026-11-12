"""Módulo de Recruiting: sus modelos (tablas y catálogos de la revisión 0006) y su entrada en el menú.

El módulo se registra en el registry (fuente de verdad del sidebar y de los permisos): los permisos que se asignan
a los grupos son 'recruiting' y 'recruiting.<codigo>' de cada ítem. Routers y pantallas llegan con la incorporación
del resto del módulo.

Los ítems van con ruta=None: todavía no hay un blueprint de Recruiting en el frontend, y el sidebar resuelve cada
ruta con url_for, que fallaría para todos los usuarios con un endpoint inexistente. Con ruta=None se muestran como
"Próx." (igual que los pendientes de Nómina). Cuando exista el blueprint, se completa 'ruta' con su endpoint
(recruiting.dashboard, recruiting.candidatos, recruiting.oportunidades, recruiting.gestion_busquedas y
recruiting.parametros, los del módulo original).
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
            "ruta": None,
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
