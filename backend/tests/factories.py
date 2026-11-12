import uuid
from collections.abc import Iterable

from sqlalchemy.orm import Session

from backend.modules.empresa.models import Empresa, core_usuario_empresa
from backend.modules.nomina.models import Empleado
from backend.modules.permisos.models import Grupo, PermisoModulo, usuario_grupo
from backend.modules.usuarios.models import Usuario


class CoreDataFactory:
    """Creates explicit, minimal domain data for integration tests."""

    def __init__(self, session: Session):
        self.session = session

    def usuario(
        self,
        *,
        email: str | None = None,
        email_secundario: str | None = None,
        password: str = "test-password",
        nombre: str = "Test",
        apellido: str = "User",
        rol: str = "usuario",
        activo: bool = True,
        dni: int | None = None,
    ) -> Usuario:
        usuario = Usuario(
            email=email or f"test-{uuid.uuid4().hex}@example.com",
            email_secundario=email_secundario,
            nombre=nombre,
            apellido=apellido,
            rol=rol,
            activo=activo,
            dni=dni,
        )
        usuario.set_password(password)
        self.session.add(usuario)
        self.session.flush()
        return usuario

    def empresa(
        self,
        *,
        cuit: str | None = None,
        razon_social: str = "Empresa Test SA",
        nombre_fantasia: str = "Empresa Test",
        responsabilidad_afip: str = "Responsable Inscripto",
        activo: bool = True,
    ) -> Empresa:
        empresa = Empresa(
            cuit=cuit or self._unique_cuit(),
            razon_social=razon_social,
            nombre_fantasia=nombre_fantasia,
            responsabilidad_afip=responsabilidad_afip,
            activo=activo,
        )
        self.session.add(empresa)
        self.session.flush()
        return empresa

    def asignar_empresa(self, usuario: Usuario, empresa: Empresa) -> None:
        self.session.execute(
            core_usuario_empresa.insert().values(
                usuario_id=usuario.id,
                empresa_id=empresa.id,
            )
        )
        self.session.flush()

    def grupo(
        self,
        *,
        nombre: str | None = None,
        descripcion: str = "Grupo creado por tests",
        activo: bool = True,
    ) -> Grupo:
        grupo = Grupo(
            nombre=nombre or f"grupo-test-{uuid.uuid4().hex}",
            descripcion=descripcion,
            activo=activo,
        )
        self.session.add(grupo)
        self.session.flush()
        return grupo

    def asignar_grupo(
        self,
        usuario: Usuario,
        grupo: Grupo,
        empresa: Empresa,
    ) -> None:
        self.session.execute(
            usuario_grupo.insert().values(
                usuario_id=usuario.id,
                grupo_id=grupo.id,
                empresa_id=empresa.id,
            )
        )
        self.session.flush()

    def permisos(
        self,
        grupo: Grupo,
        modulos: Iterable[str],
        *,
        tiene_acceso: bool = True,
    ) -> list[PermisoModulo]:
        permisos = [
            PermisoModulo(
                grupo_id=grupo.id,
                modulo=modulo,
                tiene_acceso=tiene_acceso,
            )
            for modulo in modulos
        ]
        self.session.add_all(permisos)
        self.session.flush()
        return permisos

    def empleado(
        self,
        empresa: Empresa,
        *,
        nombre: str = "Ana",
        apellido: str = "Test",
        dni: int | None = None,
        email_corporativo: str | None = None,
        activo: bool = True,
    ) -> Empleado:
        valor = uuid.uuid4().int
        empleado = Empleado(
            empresa_id=empresa.id,
            codigo=f"EMP-{uuid.uuid4().hex[:10]}",
            cuil=20_000_000_000 + valor % 9_999_999_999,
            nombre=nombre,
            apellido=apellido,
            dni=dni if dni is not None else 10_000_000 + valor % 89_999_999,
            email_corporativo=email_corporativo,
            activo=activo,
        )
        self.session.add(empleado)
        self.session.flush()
        return empleado

    @staticmethod
    def _unique_cuit() -> str:
        value = uuid.uuid4().int % 100_000_000
        return f"30-{value:08d}-7"
