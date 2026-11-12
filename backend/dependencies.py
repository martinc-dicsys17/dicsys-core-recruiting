"""
Dependencias comunes de FastAPI.
"""

import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.tokens import decodificar
from backend.database import get_db
from backend.modules.usuarios.models import Usuario

# Esquema de seguridad Bearer para Swagger (auto_error=False para manejar el error manualmente)
security = HTTPBearer(auto_error=False)


async def get_current_user(
    db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Usuario:
    """Extrae y valida el usuario desde el token JWT."""

    if not credentials:
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    # Sin propósitos permitidos: el token intermedio del 2FA no vale como sesión
    payload = decodificar(credentials.credentials)
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido")

    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not usuario or not usuario.activo:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")

    return usuario


def require_admin(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    """Requiere que el usuario sea administrador."""
    if current_user.rol != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado - se requiere rol admin")
    return current_user


async def get_empresa_activa(
    current_user: Usuario = Depends(get_current_user), credentials: HTTPAuthorizationCredentials = Depends(security)
) -> uuid.UUID:
    """Extrae empresa_id del JWT. Retorna UUID o lanza 403."""
    payload = decodificar(credentials.credentials)
    empresa_id = payload.get("empresa_id")
    if not empresa_id:
        raise HTTPException(status_code=403, detail="No se ha seleccionado una empresa")
    return uuid.UUID(empresa_id)


def require_modulo(codigo_modulo: str):
    """
    Dependency factory que verifica que el usuario tenga acceso a un módulo.
    Los admin siempre tienen acceso a todo.
    Permisos se evalúan por empresa activa del JWT.
    """

    async def _verificar(
        current_user: Usuario = Depends(get_current_user),
        db: Session = Depends(get_db),
        empresa_id: uuid.UUID = Depends(get_empresa_activa),
    ) -> Usuario:
        if current_user.rol == "admin":
            return current_user

        from backend.modules.permisos.services import GrupoService

        permisos = GrupoService.obtener_permisos_usuario(db, str(current_user.id), empresa_id)

        if not permisos.get(codigo_modulo, False):
            raise HTTPException(status_code=403, detail=f"No tenés acceso al módulo '{codigo_modulo}'")

        return current_user

    return _verificar


def require_submodulo(codigo_modulo: str, codigo_submodulo: str):
    """
    Dependency factory que verifica acceso a un submódulo específico.
    Permisos se evalúan por empresa activa del JWT.

    Admin pasa siempre. Otros necesitan el módulo y el submódulo
    '<modulo>.<submodulo>' para la empresa activa.
    """

    async def _verificar(
        current_user: Usuario = Depends(get_current_user),
        db: Session = Depends(get_db),
        empresa_id: uuid.UUID = Depends(get_empresa_activa),
    ) -> Usuario:
        if current_user.rol == "admin":
            return current_user

        from backend.modules.permisos.services import GrupoService

        permisos = GrupoService.obtener_permisos_usuario(db, str(current_user.id), empresa_id)

        if not permisos.get(codigo_modulo, False):
            raise HTTPException(status_code=403, detail=f"No tenés acceso al módulo '{codigo_modulo}'")

        clave = f"{codigo_modulo}.{codigo_submodulo}"
        if not permisos.get(clave, False):
            raise HTTPException(status_code=403, detail=f"No tenés acceso a '{codigo_submodulo}'")

        return current_user

    return _verificar


async def get_empresa_cuit(
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    db: Session = Depends(get_db),
) -> str:
    """Retorna el CUIT (sin guiones) de la empresa activa. Para armar keys de storage."""
    from backend.modules.empresa.models import Empresa

    empresa = db.query(Empresa.cuit).filter(Empresa.id == empresa_id).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return empresa.cuit.replace("-", "")
