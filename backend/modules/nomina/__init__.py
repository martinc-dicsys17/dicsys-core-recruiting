# Módulo Nómina
from backend.core.registry import registrar_modulo

registrar_modulo(
    codigo="nomina",
    nombre="Nómina",
    icono="wallet",
    orden=2,
    items=[
        {"codigo": "empleados", "nombre": "Empleados", "icono": "users", "ruta": "nomina.empleados_list", "orden": 1},
        {
            "codigo": "departamentos",
            "nombre": "Departamentos",
            "icono": "building-2",
            "ruta": "nomina.departamentos_list",
            "orden": 2,
        },
        {"codigo": "perfiles", "nombre": "Perfiles", "icono": "briefcase", "ruta": "nomina.perfiles_list", "orden": 3},
        {"codigo": "categorias", "nombre": "Categorías", "icono": "tag", "ruta": "nomina.categorias_list", "orden": 4},
        {
            "codigo": "carreras",
            "nombre": "Carreras",
            "icono": "graduation-cap",
            "ruta": "nomina.carreras_list",
            "orden": 5,
        },
    ],
)
