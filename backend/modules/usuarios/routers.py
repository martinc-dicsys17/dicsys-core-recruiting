"""
Rutas FastAPI para usuarios.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.core.files import delete_profile_image, save_profile_image
from backend.core.limites import Intentos
from backend.database import get_db
from backend.dependencies import get_current_user, get_empresa_activa, require_submodulo
from backend.modules.usuarios.emails_corporativos import EmailInvalido
from backend.modules.usuarios.schemas import (
    AdminSetPassword,
    ChangePassword,
    MagicLinkSetPassword,
    UsuarioCreate,
    UsuarioList,
    UsuarioResponse,
    UsuarioUpdate,
)
from backend.modules.usuarios.services import UsuarioService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/usuarios", tags=["usuarios"])

require_usuarios = Depends(require_submodulo("configuracion", "usuarios"))

# Router público para magic links (sin autenticación)
public_router = APIRouter(prefix="/usuarios", tags=["usuarios-public"])


@router.get("", response_model=UsuarioList)
async def listar_usuarios(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=1000),
    activo: Optional[bool] = Query(None),
    rol: Optional[str] = Query(None),
    buscar: Optional[str] = Query(None),
    ordenar_por: Optional[str] = Query(None),
    ordenar_dir: Optional[str] = Query("asc"),
    departamento_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_usuarios,
):
    """Lista usuarios con paginación y filtros."""
    try:
        filtros = {}
        if activo is not None:
            filtros["activo"] = activo
        if rol:
            filtros["rol"] = rol
        if buscar:
            filtros["buscar"] = buscar
        if ordenar_por:
            filtros["ordenar_por"] = ordenar_por
            filtros["ordenar_dir"] = ordenar_dir
        if departamento_id:
            filtros["departamento_id"] = departamento_id
            filtros["empresa_id"] = str(empresa_id)  # para el join multiempresa

        resultado = UsuarioService.listar_usuarios(db, pagina, por_pagina, filtros)

        return UsuarioList(
            usuarios=[_usuario_con_grupos(u, db, empresa_id) for u in resultado["usuarios"]],
            total=resultado["total"],
            pagina=resultado["pagina"],
            por_pagina=resultado["por_pagina"],
            total_paginas=resultado["total_paginas"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/{usuario_id}", response_model=UsuarioResponse)
async def obtener_usuario(
    usuario_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_usuarios,
):
    """Obtiene un usuario específico por ID."""
    try:
        usuario = UsuarioService.obtener_usuario(db, usuario_id)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return _usuario_con_grupos(usuario, db, empresa_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("", response_model=UsuarioResponse, status_code=201)
async def crear_usuario(
    usuario_data: UsuarioCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_usuarios,
):
    """Crea un nuevo usuario."""
    try:
        datos = usuario_data.model_dump()
        # Usar empresa_id del form si viene, sino la empresa activa
        target_empresa_id = datos.pop("empresa_id", None)
        if target_empresa_id:
            import uuid as uuid_mod

            target_empresa_id = uuid_mod.UUID(target_empresa_id)
        else:
            target_empresa_id = empresa_id
        usuario = UsuarioService.crear_usuario(db, datos, empresa_id=target_empresa_id)
        return UsuarioResponse.model_validate(usuario)
    except EmailInvalido as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.put("/{usuario_id}", response_model=UsuarioResponse)
async def actualizar_usuario(
    usuario_id: str,
    usuario_data: UsuarioUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_usuarios,
):
    """Actualiza un usuario existente."""
    try:
        datos = usuario_data.dict(exclude_unset=True)
        if not datos:
            raise HTTPException(status_code=400, detail="No se proporcionaron datos para actualizar")

        usuario = UsuarioService.actualizar_usuario(db, usuario_id, datos, empresa_id=empresa_id)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return UsuarioResponse.model_validate(usuario)
    except HTTPException:
        raise
    except EmailInvalido as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.delete("/{usuario_id}")
async def eliminar_usuario(usuario_id: str, db: Session = Depends(get_db), current_user=require_usuarios):
    """Elimina un usuario (soft delete)."""
    try:
        if not UsuarioService.eliminar_usuario(db, usuario_id):
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return {"message": "Usuario eliminado correctamente"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.put("/{usuario_id}/password")
async def cambiar_password(
    usuario_id: str,
    password_data: ChangePassword,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Cambia la contraseña de un usuario."""
    try:
        UsuarioService.cambiar_password(db, usuario_id, password_data.password_actual, password_data.password_nueva)
        return {"message": "Contraseña cambiada correctamente"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.put("/{usuario_id}/set-password")
async def admin_set_password(
    usuario_id: str, password_data: AdminSetPassword, db: Session = Depends(get_db), current_user=require_usuarios
):
    """Permite a un admin establecer la contraseña de un usuario directamente."""
    try:
        usuario = UsuarioService.obtener_usuario(db, usuario_id)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        usuario.set_password(password_data.password)
        # Desactivar 2FA al resetear password desde admin
        if usuario.totp_enabled:
            usuario.totp_enabled = False
            usuario.totp_secret = None
            usuario.totp_backup_codes = None
        db.commit()
        return {"message": "Contraseña establecida correctamente"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/{usuario_id}/reset-2fa")
async def admin_reset_2fa(usuario_id: str, db: Session = Depends(get_db), current_user=require_usuarios):
    """Resetea el 2FA de un usuario (admin)."""
    usuario = UsuarioService.obtener_usuario(db, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    usuario.totp_enabled = False
    usuario.totp_secret = None
    usuario.totp_backup_codes = None
    usuario.totp_required = True  # Forzar que lo configure de nuevo
    db.commit()
    return {"message": "2FA reseteado"}


@router.put("/{usuario_id}/activar", response_model=UsuarioResponse)
async def activar_usuario(usuario_id: str, db: Session = Depends(get_db), current_user=require_usuarios):
    """Activa un usuario desactivado."""
    try:
        usuario = UsuarioService.actualizar_usuario(db, usuario_id, {"activo": True})
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return UsuarioResponse.model_validate(usuario)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.put("/{usuario_id}/restaurar", response_model=UsuarioResponse)
async def restaurar_usuario(usuario_id: str, db: Session = Depends(get_db), current_user=require_usuarios):
    """Restaura un usuario eliminado (soft delete)."""
    try:
        usuario = UsuarioService.restaurar_usuario(db, usuario_id)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado o no está eliminado")
        return UsuarioResponse.model_validate(usuario)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/buscar/", response_model=dict)
async def buscar_usuarios(
    q: str = Query(..., min_length=1),
    limite: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user=require_usuarios,
):
    """Busca usuarios por texto."""
    try:
        resultado = UsuarioService.listar_usuarios(db, pagina=1, por_pagina=limite, filtros={"buscar": q})
        return {
            "usuarios": [UsuarioResponse.model_validate(u) for u in resultado["usuarios"]],
            "total": resultado["total"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@public_router.get("/magic-link/validar/{token}")
async def validar_magic_link(token: str, db: Session = Depends(get_db), intentos: Intentos = Depends(Intentos)):
    """Valida si un magic link token es válido. Un enlace inválido cuenta como fallo de la IP (F07-P07)."""
    intentos.frenar()
    usuario = UsuarioService.validar_magic_link(db, token)
    if not usuario:
        intentos.contar()
        raise HTTPException(status_code=400, detail="El enlace es inválido o ha expirado")
    return {"valid": True, "email": usuario.email, "nombre": usuario.nombre}


@public_router.post("/magic-link/set-password")
async def set_password_magic_link(
    data: MagicLinkSetPassword, db: Session = Depends(get_db), intentos: Intentos = Depends(Intentos)
):
    """Establece la contraseña usando un magic link válido. Un enlace inválido cuenta como fallo de la IP (F07-P07)."""
    intentos.frenar()
    if not UsuarioService.validar_magic_link(db, data.token):
        intentos.contar()
        raise HTTPException(status_code=400, detail="El enlace es inválido o ha expirado")
    try:
        usuario = UsuarioService.establecer_password_magic_link(db, data.token, data.password)
        return {"message": "Contraseña establecida correctamente", "email": usuario.email}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/{usuario_id}/reenviar-magic-link")
async def reenviar_magic_link(usuario_id: str, db: Session = Depends(get_db), current_user=require_usuarios):
    """Reenvía el magic link de bienvenida a un usuario."""
    if not UsuarioService.reenviar_magic_link(db, usuario_id):
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"message": "Magic link reenviado correctamente"}


@router.post("/{usuario_id}/avatar", response_model=UsuarioResponse)
async def subir_avatar(
    usuario_id: str, file: UploadFile = File(...), db: Session = Depends(get_db), current_user=require_usuarios
):
    """Sube una imagen de perfil para el usuario."""
    try:
        # Obtener usuario actual
        usuario = UsuarioService.obtener_usuario(db, usuario_id)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        # Eliminar avatar anterior si existe
        if usuario.avatar_url:
            delete_profile_image(usuario.avatar_url)

        # Guardar nuevo avatar
        avatar_url = await save_profile_image(file)
        logger.info(f"Avatar guardado en: {avatar_url}")

        # Actualizar usuario directamente en la instancia y commitear
        usuario.avatar_url = avatar_url
        db.commit()
        db.refresh(usuario)
        logger.info(f"Usuario actualizado, avatar_url: {usuario.avatar_url}")

        return UsuarioResponse.model_validate(usuario)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir imagen: {str(e)}")


@router.delete("/{usuario_id}/avatar", response_model=UsuarioResponse)
async def eliminar_avatar(usuario_id: str, db: Session = Depends(get_db), current_user=require_usuarios):
    """Elimina la imagen de perfil del usuario."""
    try:
        usuario = UsuarioService.obtener_usuario(db, usuario_id)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        if usuario.avatar_url:
            delete_profile_image(usuario.avatar_url)

        usuario = UsuarioService.actualizar_usuario(db, usuario_id, {"avatar_url": None})
        return UsuarioResponse.model_validate(usuario)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


def _usuario_con_grupos(usuario, db: Session, empresa_id: uuid.UUID) -> UsuarioResponse:
    """Construye UsuarioResponse con los grupos del usuario para la empresa activa."""
    from backend.modules.nomina.models import Empleado
    from backend.modules.permisos.models import Grupo, usuario_grupo
    from backend.modules.usuarios.schemas import GrupoSimple

    grupos = (
        db.query(Grupo)
        .join(usuario_grupo, Grupo.id == usuario_grupo.c.grupo_id)
        .filter(
            usuario_grupo.c.usuario_id == usuario.id,
            usuario_grupo.c.empresa_id == empresa_id,
            Grupo.deleted_at.is_(None),
        )
        .all()
    )

    # Obtener departamento via join con Empleado por DNI
    departamento_id = None
    departamento_nombre = None
    if usuario.dni:
        empleado = db.query(Empleado).filter(Empleado.dni == usuario.dni, Empleado.deleted_at.is_(None)).first()
        if empleado and empleado.departamento_id:
            departamento_id = str(empleado.departamento_id)
            if empleado.departamento_rel:
                departamento_nombre = empleado.departamento_rel.nombre

    response = UsuarioResponse.model_validate(usuario)
    response.grupos = [GrupoSimple(id=str(g.id), nombre=g.nombre) for g in grupos]
    response.departamento_id = departamento_id
    response.departamento_nombre = departamento_nombre
    return response
