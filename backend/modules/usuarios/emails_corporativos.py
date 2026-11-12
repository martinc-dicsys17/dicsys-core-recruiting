"""Emails de la cuenta y el email corporativo de la ficha de nómina (F22).

La cuenta (`core_usuarios`) es la fuente: `email`, con el que la persona entra, y `email_secundario`, su otro dominio
(por ejemplo, el @dicsys.com de quien ya entra con @dicsys.ai). Los dos se editan solo desde Usuarios.

La ficha de nómina copia el `email` de la cuenta con su mismo DNI en `email_corporativo`, siempre que sea de un dominio
de la empresa de la ficha (si no, queda en null); en nómina es de solo lectura. Las fichas sin cuenta conservan el
email que trae Odoo hasta que la persona tenga cuenta.

Para entrar, una cuenta con DNI y ficha vigente necesita que el email o el secundario sean de un dominio de la empresa
de alguna de sus fichas.
"""

import json
from typing import List, Optional, Set

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.modules.empresa.models import Empresa, core_usuario_empresa
from backend.modules.nomina.models import Empleado
from backend.modules.usuarios.models import Usuario

DOMINIOS_POR_DEFECTO = ("dicsys.ai", "dicsys.com")  # si la empresa no tiene dominios cargados
SIN_EMAIL_CORPORATIVO = (
    "Tu usuario no tiene un email corporativo y no puede acceder a Dicsys Core. Comunicate con el administrador."
)


class EmailInvalido(ValueError):
    """Un email de la cuenta que no cumple las reglas (422)."""


def normalizar(email: Optional[str]) -> Optional[str]:
    email = (email or "").strip().lower()
    return email or None


def dominio(email: Optional[str]) -> str:
    email = normalizar(email)
    return email.rsplit("@", 1)[-1] if email and "@" in email else ""


def _comparable(columna):
    return func.lower(func.trim(columna))


def dominios_corporativos(db: Session, empresa_id) -> List[str]:
    """Los dominios de email de la empresa; sin cargar, dicsys.ai y dicsys.com."""
    valor = db.query(Empresa.dominios_email).filter(Empresa.id == empresa_id).scalar()
    try:
        dominios = [str(d).strip().lower().lstrip("@") for d in json.loads(valor or "[]") if str(d).strip()]
    except TypeError, ValueError:
        dominios = []
    return dominios or list(DOMINIOS_POR_DEFECTO)


def fichas_de(db: Session, dni: Optional[int]) -> List[Empleado]:
    """Las fichas vigentes (sin borrar, activas o dadas de baja) de ese DNI."""
    if dni is None:
        return []
    return db.query(Empleado).filter(Empleado.dni == dni, Empleado.deleted_at.is_(None)).all()


def cuenta_de_dni(db: Session, dni: Optional[int]) -> Optional[Usuario]:
    if dni is None:
        return None
    return db.query(Usuario).filter(Usuario.dni == dni, Usuario.deleted_at.is_(None)).first()


def cuentas_con_email(db: Session, email: Optional[str]) -> List[Usuario]:
    """Las cuentas vigentes que tienen ese email como email o como secundario (sin mayúsculas ni espacios)."""
    email = normalizar(email)
    if not email:
        return []
    return (
        db.query(Usuario)
        .filter(
            Usuario.deleted_at.is_(None),
            or_(_comparable(Usuario.email) == email, _comparable(Usuario.email_secundario) == email),
        )
        .all()
    )


def cuenta_con_email(db: Session, email: Optional[str]) -> Optional[Usuario]:
    """La cuenta con ese email o secundario; si lo tienen dos cuentas, ninguna."""
    cuentas = cuentas_con_email(db, email)
    return cuentas[0] if len(cuentas) == 1 else None


def fichas_con_email(db: Session, email: Optional[str]) -> List[Empleado]:
    """Las fichas vigentes con ese email corporativo (sin mayúsculas ni espacios)."""
    email = normalizar(email)
    if not email:
        return []
    return (
        db.query(Empleado).filter(Empleado.deleted_at.is_(None), _comparable(Empleado.email_corporativo) == email).all()
    )


def dominios_de_la_cuenta(db: Session, usuario: Usuario) -> Set[str]:
    """Los dominios de las empresas de sus fichas o, si no tiene fichas, de las empresas de la cuenta."""
    empresas = {ficha.empresa_id for ficha in fichas_de(db, usuario.dni)}
    if not empresas and usuario.id is not None:
        empresas = set(
            db.execute(
                select(core_usuario_empresa.c.empresa_id).where(core_usuario_empresa.c.usuario_id == usuario.id)
            ).scalars()
        )
    dominios: Set[str] = set()
    for empresa_id in empresas:
        dominios.update(dominios_corporativos(db, empresa_id))
    return dominios or set(DOMINIOS_POR_DEFECTO)


def email_para_la_ficha(db: Session, email: Optional[str], empresa_id) -> Optional[str]:
    """El email de la cuenta, si es de un dominio de la empresa de la ficha; si no, None."""
    email = normalizar(email)
    return email if email and dominio(email) in dominios_corporativos(db, empresa_id) else None


def copiar_a_fichas(db: Session, usuario: Optional[Usuario]) -> None:
    """Copia el email de la cuenta a sus fichas vigentes (por DNI). No confirma la transacción."""
    if usuario is None or usuario.dni is None or usuario.deleted_at is not None:
        return
    for ficha in fichas_de(db, usuario.dni):
        nuevo = email_para_la_ficha(db, usuario.email, ficha.empresa_id)
        if ficha.email_corporativo != nuevo:
            ficha.email_corporativo = nuevo


def copiar_desde_la_cuenta(db: Session, ficha: Empleado) -> None:
    """Una ficha nueva o con otro DNI toma el email de la cuenta de ese DNI; sin cuenta, conserva el que tiene."""
    cuenta = cuenta_de_dni(db, ficha.dni)
    if cuenta is not None:
        ficha.email_corporativo = email_para_la_ficha(db, cuenta.email, ficha.empresa_id)


def tiene_email_corporativo(db: Session, usuario: Usuario) -> bool:
    """Si la cuenta puede entrar: sin DNI o sin ficha vigente, sí; con ficha, el email o el secundario tienen que ser de
    un dominio de la empresa de alguna de sus fichas."""
    fichas = fichas_de(db, usuario.dni)
    if not fichas:
        return True
    emails = [e for e in (normalizar(usuario.email), normalizar(usuario.email_secundario)) if e]
    return any(dominio(e) in dominios_corporativos(db, ficha.empresa_id) for ficha in fichas for e in emails)


def emails_de_la_persona(db: Session, email: Optional[str]) -> List[str]:
    """Los emails de la cuenta de la persona que tiene ese email, el principal primero. Se la busca por la cuenta y,
    si no, por la ficha con ese email corporativo. Sin cuenta, solo ese email: los mensajes personales de Webex
    prueban en ese orden."""
    email = normalizar(email)
    if not email:
        return []
    cuenta = cuenta_con_email(db, email)
    if cuenta is None:
        fichas = fichas_con_email(db, email)
        cuenta = cuenta_de_dni(db, fichas[0].dni) if fichas else None
    if cuenta is None:
        return [email]
    candidatos = [normalizar(cuenta.email), normalizar(cuenta.email_secundario)]
    return [e for i, e in enumerate(candidatos) if e and e not in candidatos[:i]] or [email]


def validar_cuenta(db: Session, datos: dict, actual: Optional[Usuario] = None) -> None:
    """Normaliza en `datos` el email y el secundario que vienen y valida cómo queda la cuenta.

    EmailInvalido (422): secundario igual al email; con ficha de nómina, email o secundario de un dominio que no es de
    la empresa de la ficha. ValueError (409): el email o el secundario ya es de otra cuenta.
    """
    if not any(campo in datos for campo in ("email", "email_secundario", "dni")):
        return
    for campo in ("email", "email_secundario"):
        if campo in datos:
            datos[campo] = normalizar(datos[campo])
    principal = datos["email"] if "email" in datos else normalizar(actual.email if actual else None)
    secundario = (
        datos["email_secundario"]
        if "email_secundario" in datos
        else normalizar(actual.email_secundario if actual else None)
    )

    if secundario and secundario == principal:
        raise EmailInvalido("El email secundario tiene que ser distinto del email")

    dni = datos["dni"] if "dni" in datos else (actual.dni if actual else None)
    fichas = fichas_de(db, dni)
    if fichas:
        dominios: List[str] = []
        for ficha in fichas:
            dominios += [d for d in dominios_corporativos(db, ficha.empresa_id) if d not in dominios]
        for campo, email, nombre in (
            ("email", principal, "El email"),
            ("email_secundario", secundario, "El email secundario"),
        ):
            if email and (campo in datos or "dni" in datos) and dominio(email) not in dominios:
                raise EmailInvalido(
                    f"{nombre} tiene que ser de un dominio de la empresa "
                    f"({', '.join('@' + d for d in dominios)}): la persona tiene ficha de nómina"
                )

    for campo, email, mensaje in (
        ("email", principal, "El email ya está registrado"),
        ("email_secundario", secundario, "El email secundario ya es de otra cuenta"),
    ):
        if email and campo in datos and any(actual is None or c.id != actual.id for c in cuentas_con_email(db, email)):
            raise ValueError(mensaje)
