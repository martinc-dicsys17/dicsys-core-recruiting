"""Módulo de gestión de permisos y grupos."""

from backend.core.registry import registrar_modulo
from backend.modules.permisos.models import Grupo, PermisoModulo, usuario_grupo

registrar_modulo(
    codigo="configuracion",
    nombre="Configuración",
    icono="settings",
    orden=1,
    items=[
        {
            "codigo": "empresas",
            "nombre": "Empresas",
            "icono": "building-2",
            "ruta": "empresa.empresas_list",
            "orden": 1,
        },
        {"codigo": "usuarios", "nombre": "Usuarios", "icono": "users", "ruta": "usuarios.list", "orden": 2},
        {
            "codigo": "permisos",
            "nombre": "Permisos",
            "icono": "shield-check",
            "ruta": "permisos.grupos_list",
            "orden": 3,
        },
        {
            "codigo": "actualizacion_datos",
            "nombre": "Actualización de Datos",
            "icono": "refresh-cw",
            "ruta": "sincronizacion.listar",
            "orden": 4,
        },
        {"codigo": "llm", "nombre": "LLM Usage", "icono": "sparkles", "ruta": "llm.usage", "orden": 5},
        {
            "codigo": "parametros",
            "nombre": "Parámetros",
            "icono": "sliders-horizontal",
            "ruta": "parametros.listar",
            "orden": 6,
        },
        {
            "codigo": "notificaciones",
            "nombre": "Notificaciones",
            "icono": "bell",
            "ruta": "notificaciones.cumpleanos",
            "orden": 7,
        },
        {
            "codigo": "tareas_programadas",
            "nombre": "Tareas programadas",
            "icono": "alarm-clock",
            "ruta": "tareas.listar",
            "orden": 8,
        },
    ],
)

__all__ = ["Grupo", "PermisoModulo", "usuario_grupo"]
