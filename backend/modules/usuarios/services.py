"""
Servicios de negocio para usuarios.
"""

import logging
import math
import secrets
import uuid
from datetime import timedelta
from typing import Any, Dict, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.email import email_service
from backend.core.utils import utc_now
from backend.modules.permisos.models import Grupo, usuario_grupo
from backend.modules.usuarios import emails, emails_corporativos, secretos
from backend.modules.usuarios.models import Usuario

logger = logging.getLogger(__name__)

# Constantes de configuración
MAGIC_LINK_EXPIRATION_HOURS = 48


class UsuarioService:
    """Servicio para operaciones CRUD de usuarios."""

    @staticmethod
    def crear_usuario(
        db: Session, datos: Dict[str, Any], usuario_actual: str = None, empresa_id: uuid.UUID = None
    ) -> Usuario:
        """Crea un nuevo usuario en la base de datos."""
        try:
            # Validar email único entre usuarios activos (no soft-deleted)
            email = datos.get("email")
            if email:
                usuario_existente = (
                    db.query(Usuario).filter(Usuario.email == email, Usuario.deleted_at.is_(None)).first()
                )
                if usuario_existente:
                    raise ValueError("El email ya está registrado")

            # Validar DNI único entre usuarios activos (no soft-deleted)
            dni = datos.get("dni")
            if dni:
                usuario_dni = db.query(Usuario).filter(Usuario.dni == dni, Usuario.deleted_at.is_(None)).first()
                if usuario_dni:
                    raise ValueError("El DNI ya está registrado")

            # Secundario, dominios de la empresa si tiene ficha y repetidos (F22)
            emails_corporativos.validar_cuenta(db, datos)

            password = datos.pop("password", None)
            solicitar_password = datos.pop("solicitar_password", False)
            grupo_ids = datos.pop("grupo_ids", None)

            if usuario_actual:
                datos["updated_by"] = usuario_actual

            usuario = Usuario(**datos)

            # Si solicitar_password está activo, generamos magic link: en la base solo su hash
            magic_token = None
            if solicitar_password:
                usuario.requiere_password_change = True
                magic_token, usuario.magic_link_token = secretos.nuevo_magic_link()
                usuario.magic_link_expires = utc_now() + timedelta(hours=MAGIC_LINK_EXPIRATION_HOURS)
                # Password temporal random (el usuario lo cambiará)
                usuario.set_password(secrets.token_urlsafe(16))
            elif password:
                usuario.set_password(password)
            else:
                raise ValueError("Debe proporcionar una contraseña o marcar solicitar_password")

            db.add(usuario)
            db.flush()
            # La ficha de nómina con su DNI copia el email de la cuenta (F22)
            emails_corporativos.copiar_a_fichas(db, usuario)
            db.commit()
            db.refresh(usuario)

            # Asociar usuario a la empresa activa
            if empresa_id:
                from backend.modules.empresa.models import core_usuario_empresa

                ya_vinculado = db.execute(
                    core_usuario_empresa.select().where(
                        core_usuario_empresa.c.usuario_id == usuario.id,
                        core_usuario_empresa.c.empresa_id == empresa_id,
                    )
                ).first()
                if not ya_vinculado:
                    db.execute(
                        core_usuario_empresa.insert().values(
                            usuario_id=usuario.id, empresa_id=empresa_id, created_at=utc_now()
                        )
                    )
                    db.commit()

            # Asignar grupos de permisos (por empresa)
            if grupo_ids and empresa_id:
                grupos = (
                    db.query(Grupo)
                    .filter(Grupo.id.in_([uuid.UUID(gid) for gid in grupo_ids]), Grupo.deleted_at.is_(None))
                    .all()
                )
                for grupo in grupos:
                    db.execute(
                        usuario_grupo.insert().values(
                            usuario_id=usuario.id, grupo_id=grupo.id, empresa_id=empresa_id, created_at=utc_now()
                        )
                    )
                db.commit()
                db.refresh(usuario)

            # Enviar email de bienvenida
            if solicitar_password:
                UsuarioService._enviar_email_bienvenida(usuario, magic_token)
            elif password:
                UsuarioService._enviar_email_bienvenida_con_password(usuario, password)

            return usuario

        except IntegrityError as e:
            db.rollback()
            error_msg = str(e.orig).lower()
            if "email" in error_msg and "unique" in error_msg:
                raise ValueError("El email ya está registrado")
            elif "dni" in error_msg and "unique" in error_msg:
                raise ValueError("El DNI ya está registrado")
            else:
                raise ValueError("Error de integridad en los datos")
        except Exception as e:
            db.rollback()
            raise e

    @staticmethod
    def _construir_magic_url(token: str) -> str:
        """Construye la URL del magic link."""
        base_url = settings.frontend_url
        return f"{base_url}/set-password?token={token}"

    @staticmethod
    def _construir_login_url() -> str:
        """Construye la URL de login."""
        base_url = settings.frontend_url
        return f"{base_url}/login"

    @staticmethod
    def _enviar_email_bienvenida_con_password(usuario: Usuario, password: str) -> bool:
        """
        Envía email de bienvenida con las credenciales de acceso.

        Args:
            usuario: Usuario al que enviar el email
            password: Contraseña en texto plano para incluir en el email

        Returns:
            bool: True si se envió correctamente, False en caso contrario
        """
        logger.info(f"📧 Enviando email de bienvenida con credenciales a {usuario.email}")

        try:
            login_url = UsuarioService._construir_login_url()

            html_content = emails.bienvenida_con_password(
                nombre=usuario.nombre,
                email=usuario.email,
                password=password,
                login_url=login_url,
            )

            email_service.send(
                to=usuario.email,
                subject=f"¡Bienvenido a {settings.app_name}! - Tus credenciales de acceso",
                html=html_content,
            )

            logger.info(f"✅ Email de bienvenida con credenciales enviado a {usuario.email}")
            return True

        except FileNotFoundError as e:
            logger.error(f"❌ Template de email no encontrado: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error enviando email de bienvenida a {usuario.email}: {e}")
            return False

    @staticmethod
    def _enviar_email_bienvenida(usuario: Usuario, magic_token: Optional[str]) -> bool:
        """
        Envía email de bienvenida con magic link para establecer contraseña.

        Args:
            usuario: Usuario al que enviar el email
            magic_token: el token en claro (en la base solo está su hash); no se loguea

        Returns:
            bool: True si se envió correctamente, False en caso contrario
        """
        logger.info(f"📧 Iniciando envío de email de bienvenida a {usuario.email}")

        if not magic_token:
            logger.warning(f"⚠️ Usuario {usuario.id} sin magic link para el email de bienvenida")
            return False

        try:
            magic_url = UsuarioService._construir_magic_url(magic_token)

            html_content = emails.bienvenida(
                nombre=usuario.nombre,
                email=usuario.email,
                magic_url=magic_url,
                expiracion_horas=MAGIC_LINK_EXPIRATION_HOURS,
            )
            logger.debug("📧 Template renderizado correctamente")

            email_service.send(
                to=usuario.email,
                subject=f"¡Bienvenido a {settings.app_name}! - Configura tu contraseña",
                html=html_content,
            )

            logger.info(f"✅ Email de bienvenida enviado a {usuario.email}")
            return True

        except FileNotFoundError as e:
            logger.error(f"❌ Template de email no encontrado: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Error enviando email de bienvenida a {usuario.email}: {e}")
            return False

    @staticmethod
    def validar_magic_link(db: Session, token: str) -> Optional[Usuario]:
        """Valida un magic link token y retorna el usuario si es válido."""
        if not token:
            return None
        usuario = (
            db.query(Usuario)
            .filter(Usuario.magic_link_token == secretos.hash_magic_link(token), Usuario.deleted_at.is_(None))
            .first()
        )

        if not usuario:
            return None

        # Verificar expiración
        if usuario.magic_link_expires and usuario.magic_link_expires < utc_now():
            return None

        return usuario

    @staticmethod
    def establecer_password_magic_link(db: Session, token: str, password: str) -> Usuario:
        """Establece la contraseña usando un magic link válido."""
        usuario = UsuarioService.validar_magic_link(db, token)

        if not usuario:
            raise ValueError("El enlace es inválido o ha expirado")

        try:
            usuario.set_password(password)
            usuario.requiere_password_change = False
            usuario.magic_link_token = None
            usuario.magic_link_expires = None
            usuario.updated_at = utc_now()

            db.commit()
            db.refresh(usuario)
            return usuario
        except Exception as e:
            db.rollback()
            raise e

    @staticmethod
    def reenviar_magic_link(db: Session, usuario_id: str) -> bool:
        """Reenvía el magic link a un usuario."""
        try:
            usuario = (
                db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id), Usuario.deleted_at.is_(None)).first()
            )

            if not usuario:
                return False

            # Generar nuevo token (en la base solo su hash)
            magic_token, usuario.magic_link_token = secretos.nuevo_magic_link()
            usuario.magic_link_expires = utc_now() + timedelta(hours=MAGIC_LINK_EXPIRATION_HOURS)
            usuario.requiere_password_change = True

            db.commit()

            # Enviar email
            UsuarioService._enviar_email_bienvenida(usuario, magic_token)
            return True
        except Exception:
            db.rollback()
            return False

    @staticmethod
    def obtener_usuario(db: Session, usuario_id: str, incluir_eliminados: bool = False) -> Optional[Usuario]:
        """Obtiene un usuario por su ID."""
        try:
            query = db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id))
            if not incluir_eliminados:
                query = query.filter(Usuario.deleted_at.is_(None))
            return query.first()
        except ValueError:
            return None

    @staticmethod
    def obtener_usuario_por_email(db: Session, email: str, incluir_eliminados: bool = False) -> Optional[Usuario]:
        """Obtiene un usuario por su email."""
        query = db.query(Usuario).filter(Usuario.email == email)
        if not incluir_eliminados:
            query = query.filter(Usuario.deleted_at.is_(None))
        return query.first()

    @staticmethod
    def obtener_usuario_para_ingreso(db: Session, email: str) -> Optional[Usuario]:
        """El usuario con ese email o, si no hay, la cuenta que lo tiene como email o secundario, sin distinguir
        mayúsculas ni espacios (F22): así se entra también con el otro dominio. Si lo tienen dos cuentas, ninguna."""
        usuario = UsuarioService.obtener_usuario_por_email(db, email)
        if usuario is not None or not email:
            return usuario
        return emails_corporativos.cuenta_con_email(db, email)

    @staticmethod
    def listar_usuarios(
        db: Session, pagina: int = 1, por_pagina: int = 20, filtros: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Lista usuarios con paginación y filtros."""
        from backend.modules.nomina.models import Empleado

        query = db.query(Usuario).filter(Usuario.deleted_at.is_(None))

        if filtros:
            if "activo" in filtros:
                query = query.filter(Usuario.activo == filtros["activo"])
            if "rol" in filtros:
                query = query.filter(Usuario.rol == filtros["rol"])
            if "buscar" in filtros:
                buscar = f"%{filtros['buscar']}%"
                dni_buscar = None
                try:
                    dni_buscar = int(filtros["buscar"])
                except ValueError, TypeError:
                    pass

                condiciones = [
                    Usuario.nombre.ilike(buscar),
                    Usuario.apellido.ilike(buscar),
                    Usuario.email.ilike(buscar),
                ]
                if dni_buscar:
                    condiciones.append(Usuario.dni == dni_buscar)

                query = query.filter(or_(*condiciones))

            if "departamento_id" in filtros and filtros["departamento_id"]:
                try:
                    dep_uuid = uuid.UUID(filtros["departamento_id"])
                    query = query.join(
                        Empleado,
                        (Empleado.dni == Usuario.dni)
                        & (Empleado.deleted_at.is_(None))
                        & (Empleado.empresa_id == filtros.get("empresa_id")),
                        isouter=True,
                    ).filter(Empleado.departamento_id == dep_uuid)
                except ValueError, AttributeError:
                    pass

        total = query.count()

        # Ordenamiento
        ordenar_por = filtros.get("ordenar_por") if filtros else None
        ordenar_dir = filtros.get("ordenar_dir", "asc") if filtros else "asc"

        if ordenar_por == "nombre":
            orden = Usuario.nombre.asc() if ordenar_dir == "asc" else Usuario.nombre.desc()
        elif ordenar_por == "apellido":
            orden = Usuario.apellido.asc() if ordenar_dir == "asc" else Usuario.apellido.desc()
        elif ordenar_por == "email":
            orden = Usuario.email.asc() if ordenar_dir == "asc" else Usuario.email.desc()
        else:
            orden = Usuario.created_at.desc()

        query = query.order_by(orden)
        offset = (pagina - 1) * por_pagina
        usuarios = query.offset(offset).limit(por_pagina).all()
        total_paginas = math.ceil(total / por_pagina) if total > 0 else 1

        return {
            "usuarios": usuarios,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": total_paginas,
        }

    @staticmethod
    def actualizar_usuario(
        db: Session, usuario_id: str, datos: Dict[str, Any], usuario_actual: str = None, empresa_id: uuid.UUID = None
    ) -> Optional[Usuario]:
        """Actualiza un usuario existente."""
        try:
            usuario = db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id)).first()
            if not usuario:
                return None

            # Validar email único entre usuarios activos (no soft-deleted)
            if "email" in datos and datos["email"] != usuario.email:
                usuario_existente = (
                    db.query(Usuario)
                    .filter(Usuario.email == datos["email"], Usuario.id != usuario.id, Usuario.deleted_at.is_(None))
                    .first()
                )
                if usuario_existente:
                    raise ValueError("El email ya está registrado")

            # Validar DNI único entre usuarios activos (no soft-deleted)
            if "dni" in datos and datos["dni"] and datos["dni"] != usuario.dni:
                usuario_dni = (
                    db.query(Usuario)
                    .filter(Usuario.dni == datos["dni"], Usuario.id != usuario.id, Usuario.deleted_at.is_(None))
                    .first()
                )
                if usuario_dni:
                    raise ValueError("El DNI ya está registrado")

            # Secundario, dominios de la empresa si tiene ficha y repetidos (F22)
            emails_corporativos.validar_cuenta(db, datos, actual=usuario)

            # Extraer grupo_ids antes de iterar campos
            grupo_ids = datos.pop("grupo_ids", None)

            for campo, valor in datos.items():
                if hasattr(usuario, campo) and campo != "id":
                    setattr(usuario, campo, valor)

            # La ficha de nómina con su DNI copia el email de la cuenta (F22)
            if "email" in datos or "dni" in datos:
                emails_corporativos.copiar_a_fichas(db, usuario)

            # Asignar grupos de permisos (por empresa)
            if grupo_ids is not None and empresa_id:
                # Borrar asignaciones existentes de este usuario+empresa
                db.execute(
                    usuario_grupo.delete().where(
                        usuario_grupo.c.usuario_id == usuario.id, usuario_grupo.c.empresa_id == empresa_id
                    )
                )
                # Insertar nuevas asignaciones
                if grupo_ids:
                    grupos = (
                        db.query(Grupo)
                        .filter(Grupo.id.in_([uuid.UUID(gid) for gid in grupo_ids]), Grupo.deleted_at.is_(None))
                        .all()
                    )
                    for grupo in grupos:
                        db.execute(
                            usuario_grupo.insert().values(
                                usuario_id=usuario.id, grupo_id=grupo.id, empresa_id=empresa_id, created_at=utc_now()
                            )
                        )

            usuario.updated_at = utc_now()
            if usuario_actual:
                usuario.updated_by = usuario_actual

            db.commit()
            db.refresh(usuario)
            return usuario

        except ValueError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise e

    @staticmethod
    def eliminar_usuario(db: Session, usuario_id: str) -> bool:
        """Elimina un usuario (soft delete con deleted_at)."""
        try:
            usuario = (
                db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id), Usuario.deleted_at.is_(None)).first()
            )
            if not usuario:
                return False

            usuario.deleted_at = utc_now()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @staticmethod
    def restaurar_usuario(db: Session, usuario_id: str) -> Optional[Usuario]:
        """Restaura un usuario eliminado."""
        try:
            usuario = (
                db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id), Usuario.deleted_at.isnot(None)).first()
            )
            if not usuario:
                return None

            usuario.deleted_at = None
            usuario.updated_at = utc_now()
            db.commit()
            db.refresh(usuario)
            return usuario
        except Exception:
            db.rollback()
            return None

    @staticmethod
    def cambiar_password(db: Session, usuario_id: str, password_actual: str, password_nueva: str) -> bool:
        """Cambia la contraseña de un usuario."""
        try:
            usuario = db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id)).first()
            if not usuario:
                raise ValueError("Usuario no encontrado")

            if not usuario.verify_password(password_actual):
                raise ValueError("Contraseña actual incorrecta")

            usuario.set_password(password_nueva)
            usuario.updated_at = utc_now()

            db.commit()
            return True

        except ValueError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise e

    @staticmethod
    def actualizar_ultimo_login(db: Session, usuario_id: str) -> None:
        """Actualiza la fecha de último login."""
        UsuarioService.actualizar_usuario(db, usuario_id, {"ultimo_login": utc_now()})

    @staticmethod
    def contar_usuarios(db: Session, incluir_eliminados: bool = False) -> int:
        """Cuenta el total de usuarios en la base de datos."""
        query = db.query(Usuario)
        if not incluir_eliminados:
            query = query.filter(Usuario.deleted_at.is_(None))
        return query.count()

    @staticmethod
    def crear_usuario_admin_default(db: Session) -> Optional[Usuario]:
        """
        Crea un usuario admin por defecto si no existe ningún usuario.
        Los datos se definen en backend/core/seed_data.py → ADMIN_DEFAULT_SEED
        """
        # Verificar si ya hay usuarios
        if UsuarioService.contar_usuarios(db) > 0:
            return None

        from backend.core.seed_data import ADMIN_DEFAULT_SEED

        datos_admin = dict(ADMIN_DEFAULT_SEED)
        # Nunca una contraseña fija en el código: la de SEED_ADMIN_PASSWORD o una aleatoria que no se muestra
        datos_admin["password"] = settings.seed_admin_password or secrets.token_urlsafe(24)

        try:
            usuario_admin = UsuarioService.crear_usuario(db, datos_admin, "sistema")
            return usuario_admin
        except ValueError:
            # El usuario ya existe
            return None
