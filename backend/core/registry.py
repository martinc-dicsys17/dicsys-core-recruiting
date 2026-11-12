"""
Registry de módulos del sistema.
Cada módulo se auto-registra al importarse con su metadata y submódulos.
El sidebar y los permisos se arman desde acá (fuente de verdad única).
"""

from typing import Dict, List, Optional

# Registry global
_MODULOS_REGISTRY: Dict[str, dict] = {}


def registrar_modulo(codigo: str, nombre: str, icono: str = "box", orden: int = 99, items: Optional[List[dict]] = None):
    """
    Registra un módulo en el sistema.

    Args:
        codigo: Identificador único del módulo (ej: 'nomina')
        nombre: Nombre para mostrar (ej: 'Nómina')
        icono: Nombre del icono lucide (ej: 'wallet')
        orden: Orden en el sidebar
        items: Lista de submódulos/items con:
            - codigo: str (ej: 'empleados')
            - nombre: str (ej: 'Empleados')
            - icono: str (ej: 'users')
            - ruta: str (ej: 'nomina.empleados_list') - ruta Flask del frontend
            - orden: int
            - items: list (opcional) - hijos con la misma forma, para un tercer
              nivel en el sidebar. La clave de permiso de un hijo sigue siendo
              '<modulo>.<codigo_hijo>': el anidado es solo de presentación.
    """
    _MODULOS_REGISTRY[codigo] = {
        "codigo": codigo,
        "nombre": nombre,
        "icono": icono,
        "orden": orden,
        "items": items or [],
    }


def obtener_modulos() -> List[dict]:
    """Devuelve todos los módulos registrados, ordenados."""
    return sorted(_MODULOS_REGISTRY.values(), key=lambda m: m["orden"])


def obtener_modulo(codigo: str) -> Optional[dict]:
    """Devuelve un módulo por su código."""
    return _MODULOS_REGISTRY.get(codigo)


def items_planos(modulo: dict) -> List[dict]:
    """Ítems del módulo con sus hijos al mismo nivel, en orden de sidebar.

    Cada hijo lleva 'padre' con el código de su ítem padre. Sirve a quien
    necesita todas las claves de permiso '<modulo>.<item>' de un módulo.
    """
    planos = []
    for item in sorted(modulo.get("items", []), key=lambda i: i.get("orden", 0)):
        planos.append(item)
        for hijo in sorted(item.get("items", []), key=lambda i: i.get("orden", 0)):
            planos.append({**hijo, "padre": item["codigo"]})
    return planos
