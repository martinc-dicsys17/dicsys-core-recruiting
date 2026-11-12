"""
Routers para menús del sistema.
Lee del registry y filtra por permisos del usuario.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.registry import obtener_modulos
from backend.database import get_db
from backend.dependencies import get_current_user, get_empresa_activa
from backend.modules.permisos.services import GrupoService
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/menus", tags=["Menús"])


def _items_visibles(modulo: dict, items: list, permisos: dict, is_admin: bool) -> list:
    """Ítems del menú que el usuario puede ver, con sus hijos ya filtrados.

    Un ítem con hijos se muestra si tiene permiso propio o algún hijo visible.
    Sin permiso propio queda como rótulo: sin ruta y es_link en False.
    """
    visibles = []
    for item in sorted(items, key=lambda i: i.get("orden", 0)):
        hijos = _items_visibles(modulo, item.get("items", []), permisos, is_admin)
        propio = is_admin or permisos.get(f"{modulo['codigo']}.{item['codigo']}", False)
        if not propio and not hijos:
            continue
        ruta = item.get("ruta") if propio else None
        visibles.append(
            {
                "codigo": item["codigo"],
                "nombre": item["nombre"],
                "icono": item.get("icono", "circle"),
                "ruta": ruta,
                "es_link": bool(ruta),
                "orden": item.get("orden", 0),
                "items": hijos,
            }
        )
    return visibles


@router.get("", operation_id="menus_del_usuario")
def obtener_menus(
    current_user: Usuario = Depends(get_current_user),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    db: Session = Depends(get_db),
):
    """Obtiene los menús filtrados por permisos del usuario para la empresa activa."""
    return {"items": menu_del_usuario(db, current_user, empresa_id)}


def menu_del_usuario(db: Session, usuario: Usuario, empresa_id: uuid.UUID) -> list[dict]:
    """Los módulos, con sus ítems, que el usuario ve en la empresa activa: el menú de GET /menus y de GET /auth/me."""
    modulos = obtener_modulos()

    # Admin ve todo
    is_admin = usuario.rol == "admin"

    if is_admin:
        permisos = {}
        modulos_permitidos = [m["codigo"] for m in modulos]
    else:
        permisos = GrupoService.obtener_permisos_usuario(db, str(usuario.id), empresa_id)
        modulos_permitidos = [codigo for codigo, tiene in permisos.items() if tiene]

    resultado = []
    for m in modulos:
        if m["codigo"] not in modulos_permitidos:
            continue

        # Filtrar items/submódulos (y sus hijos) por permisos
        items_filtrados = _items_visibles(m, m.get("items", []), permisos, is_admin)

        # Solo incluir el módulo si tiene al menos un item visible
        if not items_filtrados and not is_admin:
            continue

        resultado.append(
            {
                "codigo": m["codigo"],
                "nombre": m["nombre"],
                "icono": m["icono"],
                "orden": m["orden"],
                "items": items_filtrados,
            }
        )

    return resultado
