"""
Rutas para permisos y grupos.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.core.registry import items_planos, obtener_modulos
from backend.core.utils import utc_now
from backend.database import get_db
from backend.dependencies import get_current_user, get_empresa_activa, require_submodulo
from backend.modules.permisos.models import Grupo
from backend.modules.permisos.schemas import (
    AsignarPermisosRequest,
    AsignarUsuariosRequest,
    GrupoCreate,
    GrupoListResponse,
    GrupoResponse,
    GrupoUpdate,
    ModuloConSubmodulos,
    ModuloDisponible,
    PermisoModuloSchema,
    SubmoduloDisponible,
    UsuarioGrupoResponse,
)
from backend.modules.permisos.services import GrupoService
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/permisos", tags=["permisos"])

require_permisos = Depends(require_submodulo("configuracion", "permisos"))


@router.get("/grupos", response_model=GrupoListResponse)
async def listar_grupos(
    solo_activos: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """Lista todos los grupos."""
    grupos = GrupoService.listar_grupos(db, solo_activos)
    return GrupoListResponse(grupos=[_grupo_to_response(g) for g in grupos], total=len(grupos))


@router.get("/grupos/{grupo_id}", response_model=GrupoResponse)
async def obtener_grupo(
    grupo_id: str,
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """Obtiene un grupo por ID."""
    grupo = GrupoService.obtener_grupo(db, grupo_id)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    return _grupo_to_response(grupo)


@router.post("/grupos", response_model=GrupoResponse, status_code=201)
async def crear_grupo(
    datos: GrupoCreate,
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """Crea un nuevo grupo."""
    try:
        grupo = GrupoService.crear_grupo(db, datos.model_dump())
        return _grupo_to_response(grupo)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/grupos/{grupo_id}", response_model=GrupoResponse)
async def actualizar_grupo(
    grupo_id: str,
    datos: GrupoUpdate,
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """Actualiza un grupo."""
    try:
        grupo = GrupoService.actualizar_grupo(db, grupo_id, datos.model_dump(exclude_unset=True))
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")
        return _grupo_to_response(grupo)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/grupos/{grupo_id}")
async def eliminar_grupo(
    grupo_id: str,
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """Elimina un grupo (soft delete)."""
    if not GrupoService.eliminar_grupo(db, grupo_id):
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    return {"message": "Grupo eliminado"}


@router.put("/grupos/{grupo_id}/restaurar", response_model=GrupoResponse)
async def restaurar_grupo(
    grupo_id: str,
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """Restaura un grupo eliminado."""
    grupo = GrupoService.restaurar_grupo(db, grupo_id)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado o no está eliminado")
    return _grupo_to_response(grupo)


@router.put("/grupos/{grupo_id}/permisos", response_model=GrupoResponse)
async def asignar_permisos(
    grupo_id: str,
    request: AsignarPermisosRequest,
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """Asigna permisos de módulos a un grupo."""
    try:
        permisos = [p.model_dump() for p in request.permisos]
        grupo = GrupoService.asignar_permisos(db, grupo_id, permisos)
        return _grupo_to_response(grupo)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/grupos/{grupo_id}/usuarios", response_model=List[UsuarioGrupoResponse])
async def obtener_usuarios_grupo(
    grupo_id: str,
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """Obtiene los usuarios de un grupo para la empresa activa."""
    usuarios = GrupoService.obtener_usuarios_grupo(db, grupo_id, empresa_id)
    return [UsuarioGrupoResponse(id=str(u.id), email=u.email, nombre=u.nombre, apellido=u.apellido) for u in usuarios]


@router.put("/grupos/{grupo_id}/usuarios", response_model=GrupoResponse)
async def asignar_usuarios(
    grupo_id: str,
    request: AsignarUsuariosRequest,
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """Asigna usuarios a un grupo para la empresa activa."""
    try:
        grupo = GrupoService.asignar_usuarios(db, grupo_id, request.usuario_ids, empresa_id)
        return _grupo_to_response(grupo)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Router público: solo requiere JWT, no módulo de configuración
public_router = APIRouter(prefix="/permisos", tags=["permisos"])


@public_router.get("/modulos", response_model=List[ModuloDisponible])
async def listar_modulos(
    # Solo JWT (via public_router), sin require_submodulo: datos de referencia
    # del registry que necesita la UI de permisos y otros contextos del sistema.
    current_user: Usuario = Depends(get_current_user),
):
    """Lista los módulos disponibles en el sistema (desde el registry)."""
    modulos = obtener_modulos()
    return [ModuloDisponible(codigo=m["codigo"], nombre=m["nombre"]) for m in modulos]


@public_router.get("/modulos/detalle", response_model=List[ModuloConSubmodulos])
async def listar_modulos_detalle(
    # Solo JWT (via public_router), sin require_submodulo: datos de referencia
    # del registry que necesita la UI de permisos granulares.
    current_user: Usuario = Depends(get_current_user),
):
    """Lista los módulos con sus submódulos (para UI de permisos granulares)."""
    modulos = obtener_modulos()
    return [
        ModuloConSubmodulos(
            codigo=m["codigo"],
            nombre=m["nombre"],
            icono=m.get("icono"),
            # Los hijos de un ítem vienen al mismo nivel, con 'padre', porque
            # su clave de permiso también es '<modulo>.<codigo>'.
            items=[
                SubmoduloDisponible(
                    codigo=item["codigo"],
                    nombre=item["nombre"],
                    icono=item.get("icono"),
                    padre=item.get("padre"),
                )
                for item in items_planos(m)
            ],
        )
        for m in modulos
    ]


@public_router.get("/mis-permisos")
async def obtener_mis_permisos(
    current_user: Usuario = Depends(get_current_user),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    db: Session = Depends(get_db),
):
    """Obtiene los permisos consolidados del usuario autenticado para la empresa activa."""
    permisos = GrupoService.obtener_permisos_usuario(db, str(current_user.id), empresa_id)
    return {"permisos": permisos}


@public_router.get("/departamentos-lista")
async def listar_departamentos_para_permisos(
    current_user: Usuario = Depends(get_current_user),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    db: Session = Depends(get_db),
):
    """Lista departamentos para el selector de filtros en la UI de permisos. Solo requiere JWT."""
    from backend.modules.nomina.models import Departamento

    deps = (
        db.query(Departamento)
        .filter(Departamento.empresa_id == empresa_id, Departamento.deleted_at.is_(None))
        .order_by(Departamento.nombre)
        .all()
    )
    return [{"id": str(d.id), "nombre": d.nombre} for d in deps]


@router.get("/grupos/{grupo_id}/departamentos")
async def obtener_departamentos_grupo(
    grupo_id: str,
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """Devuelve los departamentos vinculados a un grupo para la empresa activa."""
    from backend.modules.nomina.models import Departamento
    from backend.modules.permisos.models import grupo_departamento

    deps = (
        db.query(Departamento)
        .join(grupo_departamento, Departamento.id == grupo_departamento.c.departamento_id)
        .filter(
            grupo_departamento.c.grupo_id == uuid.UUID(grupo_id),
            grupo_departamento.c.empresa_id == empresa_id,
            Departamento.deleted_at.is_(None),
        )
        .all()
    )
    return [{"id": str(d.id), "nombre": d.nombre} for d in deps]


@router.put("/grupos/{grupo_id}/departamentos")
async def asignar_departamentos_grupo(
    grupo_id: str,
    request: Request,
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """Vincula departamentos a un grupo para auto-suscripción."""
    body = await request.json()
    departamento_ids = body.get("departamento_ids", [])
    from backend.modules.nomina.models import Departamento
    from backend.modules.permisos.models import grupo_departamento

    # Borrar vinculaciones existentes de este grupo+empresa
    db.execute(
        grupo_departamento.delete().where(
            grupo_departamento.c.grupo_id == uuid.UUID(grupo_id), grupo_departamento.c.empresa_id == empresa_id
        )
    )
    # Insertar nuevas
    for dep_id in departamento_ids:
        try:
            dep = (
                db.query(Departamento)
                .filter(
                    Departamento.id == uuid.UUID(dep_id),
                    Departamento.empresa_id == empresa_id,
                    Departamento.deleted_at.is_(None),
                )
                .first()
            )
            if dep:
                db.execute(
                    grupo_departamento.insert().values(
                        grupo_id=uuid.UUID(grupo_id),
                        departamento_id=dep.id,
                        empresa_id=empresa_id,
                        created_at=utc_now(),
                    )
                )
        except ValueError:
            continue
    db.commit()
    return {"message": "Departamentos actualizados"}


@router.get("/departamentos-permisos")
async def permisos_por_departamento(
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    db: Session = Depends(get_db),
    current_user=require_permisos,
):
    """
    Devuelve un resumen de grupos de permisos agrupados por departamento.
    Para cada departamento lista los grupos que tienen al menos un usuario de ese departamento.
    """
    from backend.modules.nomina.models import Departamento, Empleado
    from backend.modules.permisos.models import usuario_grupo

    # Traer todos los departamentos de la empresa
    departamentos = (
        db.query(Departamento)
        .filter(Departamento.empresa_id == empresa_id, Departamento.deleted_at.is_(None))
        .order_by(Departamento.nombre)
        .all()
    )

    resultado = []
    for dep in departamentos:
        # Empleados del departamento con DNI
        empleados = (
            db.query(Empleado)
            .filter(Empleado.departamento_id == dep.id, Empleado.deleted_at.is_(None), Empleado.dni.isnot(None))
            .all()
        )
        dnis = [e.dni for e in empleados]

        if not dnis:
            resultado.append(
                {"departamento_id": str(dep.id), "departamento_nombre": dep.nombre, "total_empleados": 0, "grupos": []}
            )
            continue

        # Usuarios que tienen esos DNIs
        usuarios = db.query(Usuario).filter(Usuario.dni.in_(dnis), Usuario.deleted_at.is_(None)).all()
        usuario_ids = [u.id for u in usuarios]

        if not usuario_ids:
            resultado.append(
                {
                    "departamento_id": str(dep.id),
                    "departamento_nombre": dep.nombre,
                    "total_empleados": len(empleados),
                    "grupos": [],
                }
            )
            continue

        # Grupos asignados a esos usuarios en esta empresa
        from sqlalchemy import func

        grupos_con_count = (
            db.query(Grupo, func.count(usuario_grupo.c.usuario_id).label("cantidad_usuarios"))
            .join(usuario_grupo, Grupo.id == usuario_grupo.c.grupo_id)
            .filter(
                usuario_grupo.c.usuario_id.in_(usuario_ids),
                usuario_grupo.c.empresa_id == empresa_id,
                Grupo.deleted_at.is_(None),
            )
            .group_by(Grupo.id)
            .all()
        )

        resultado.append(
            {
                "departamento_id": str(dep.id),
                "departamento_nombre": dep.nombre,
                "total_empleados": len(empleados),
                "grupos": [
                    {
                        "grupo_id": str(g.id),
                        "grupo_nombre": g.nombre,
                        "grupo_activo": g.activo,
                        "cantidad_usuarios": count,
                    }
                    for g, count in grupos_con_count
                ],
            }
        )

    return resultado


def _grupo_to_response(grupo) -> GrupoResponse:
    return GrupoResponse(
        id=str(grupo.id),
        nombre=grupo.nombre,
        descripcion=grupo.descripcion,
        activo=grupo.activo,
        created_at=grupo.created_at,
        permisos=[PermisoModuloSchema(modulo=p.modulo, tiene_acceso=p.tiene_acceso) for p in grupo.permisos],
    )
