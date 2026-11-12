# Módulo de Administración - Clientes y Recibos de Sueldo
from backend.core.registry import registrar_modulo

registrar_modulo(
    codigo="admin_contable",
    nombre="Administración",
    icono="calculator",
    orden=5,
    items=[
        {
            "codigo": "clientes",
            "nombre": "Clientes",
            "icono": "building-2",
            "ruta": "administracion.clientes_list",
            "orden": 1,
        },
        {
            "codigo": "recibos",
            "nombre": "Recibos de Sueldo",
            "icono": "file-text",
            "ruta": "administracion_recibos.recibos_list",
            "orden": 2,
        },
        {
            "codigo": "export_recibos",
            "nombre": "Exportar Recibos por Cliente",
            "icono": "package",
            "ruta": "administracion.export_recibos_list",
            "orden": 3,
        },
        # Proveedores (F18): registro y, anidados, su evaluación por campañas.
        # Los hijos tienen su propia clave de permiso: admin_contable.<codigo>.
        {
            "codigo": "proveedores",
            "nombre": "Proveedores",
            "icono": "truck",
            "ruta": "administracion.proveedores_list",
            "orden": 4,
            "items": [
                {
                    "codigo": "evaluacion_proveedores",
                    "nombre": "Evaluación de Proveedores",
                    "icono": "clipboard-check",
                    "ruta": "administracion.evaluaciones_proveedores",
                    "orden": 1,
                },
                {
                    "codigo": "evaluacion_config",
                    "nombre": "Configuración",
                    "icono": "settings-2",
                    "ruta": "administracion.config_evaluaciones_proveedores",
                    "orden": 2,
                },
            ],
        },
    ],
)
