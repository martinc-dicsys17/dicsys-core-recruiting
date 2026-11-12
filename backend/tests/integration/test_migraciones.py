"""Cadena de migraciones de Alembic (F04): lo que corre en un release, sobre bases nuevas de verdad.

Los demás tests arman el esquema con create_all (rápido). Acá cada test crea su propia base vacía en el mismo servidor
y la borra al terminar: upgrade desde cero, `alembic check` (modelos == migraciones), downgrade y vuelta, y la adopción
de una base de antes de Alembic (stamp 0001 + upgrade head).
"""

import json
import uuid
from pathlib import Path
from types import ModuleType

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

import backend.models_registry
from backend.database import Base, engine
from backend.modules.oidc.models import ClienteOIDC
from backend.modules.usuarios import secretos
from backend.tests.factories import CoreDataFactory

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]

BACKEND = Path(__file__).resolve().parents[2]


def _config(conexion=None) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes.update(connection=conexion, configurar_logging=False)
    return config


def _alembic(conexion, comando: str, *argumentos) -> None:
    """Un comando de Alembic en su propia transacción, como en la línea de comandos."""
    conexion.commit()
    getattr(command, comando)(_config(conexion), *argumentos)


def revision(numero: str) -> ModuleType:
    """El módulo de una revisión, para usar sus constantes en los tests."""
    return ScriptDirectory.from_config(_config()).get_revision(numero).module


MIGRACIONES_AD_HOC = revision("0002").MIGRACIONES_AD_HOC


@pytest.fixture
def base_nueva():
    nombre = f"test_migraciones_{uuid.uuid4().hex[:12]}"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
        admin.execute(text(f'CREATE DATABASE "{nombre}"'))
    motor = create_engine(engine.url.set(database=nombre))
    try:
        with motor.connect() as conexion:
            yield conexion
    finally:
        motor.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
            admin.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))


# Cómo están las bases viejas en lo que create_all no alineaba (lo corrige la adopción, revisión 0002)
DERIVAS_DE_LAS_BASES_VIEJAS = (
    "ALTER TABLE soporte_tickets DROP CONSTRAINT uq_ticket_empresa_numero",
    "ALTER TABLE soporte_tickets ADD CONSTRAINT soporte_tickets_numero_key UNIQUE (numero)",
    "ALTER TABLE soporte_pedidos_compra DROP CONSTRAINT uq_pedido_empresa_numero",
    "ALTER TABLE soporte_pedidos_compra ADD CONSTRAINT soporte_pedidos_compra_numero_key UNIQUE (numero)",
    "ALTER TABLE innovacion_licencias RENAME CONSTRAINT innovacion_licencias_pkey TO admin_licencias_pkey",
    "ALTER TABLE innovacion_licencias RENAME CONSTRAINT innovacion_licencias_empleado_id_fkey "
    "TO admin_licencias_empleado_id_fkey",
    "ALTER TABLE innovacion_licencias RENAME CONSTRAINT innovacion_licencias_empresa_id_fkey "
    "TO admin_licencias_empresa_id_fkey",
    "ALTER TABLE soporte_matriz_estado ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE starmiles_desafios ALTER COLUMN inscripcion_unica_por_empleado SET DEFAULT FALSE",
)


# Tablas que nacieron con una revisión después de la adopción: ninguna base de antes de Alembic las tuvo
NACIDAS_CON_ALEMBIC = {
    "auth_refresh_tokens",  # 0005
    # 0006: módulo Recruiting
    "recruiting_candidatos",
    "recruiting_candidatos_duplicados",
    "recruiting_ciudades",
    "recruiting_config",
    "recruiting_etapa_archivos",
    "recruiting_etapas",
    "recruiting_gestionBusqueda",
    "recruiting_habilidades",
    "recruiting_historial_cargas_cv",
    "recruiting_historial_cargas_cv_archivos",
    "recruiting_historial_pipeline",
    "recruiting_lideres",
    "recruiting_motivos_descarte",
    "recruiting_motivos_descarte_etapas",
    "recruiting_niveles_seniority",
    "recruiting_oportunidades",
    "recruiting_perfiles_puesto",
    "recruiting_postulaciones",
    "recruiting_provincias",
    "recruiting_reclutadores",
    "recruiting_skills",
    "recruiting_transiciones_estado",
}


def _base_de_antes_de_alembic(conexion, aplicadas=MIGRACIONES_AD_HOC) -> None:
    """Lo que dejaba el backend al arrancar antes de F04: el esquema, sus derivas y core_schema_migrations."""
    Base.metadata.create_all(
        bind=conexion, tables=[t for t in Base.metadata.sorted_tables if t.name not in NACIDAS_CON_ALEMBIC]
    )
    for sentencia in DERIVAS_DE_LAS_BASES_VIEJAS:
        conexion.execute(text(sentencia))
    conexion.execute(
        text("""
        CREATE TABLE core_schema_migrations (
            id VARCHAR(150) PRIMARY KEY, applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    )
    for migracion in aplicadas:
        conexion.execute(text("INSERT INTO core_schema_migrations (id) VALUES (:id)"), {"id": migracion})
    conexion.commit()


def test_una_sola_cabeza_y_revisiones_correlativas():
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1, "dos ramas con revisiones nuevas: renumerar antes de unirlas"
    revisiones = [r.revision for r in script.walk_revisions()][::-1]
    assert revisiones == [f"{n:04d}" for n in range(1, len(revisiones) + 1)]


def test_el_registro_importa_todos_los_archivos_de_modelos():
    registrados = {m.__name__ for m in vars(backend.models_registry).values() if isinstance(m, ModuleType)}
    archivos = sorted((BACKEND / "modules").rglob("*models.py"))
    nombres = {".".join(a.relative_to(BACKEND.parent).with_suffix("").parts) for a in archivos}
    assert nombres and nombres <= registrados, f"falta en backend/models_registry.py: {sorted(nombres - registrados)}"


def test_upgrade_desde_cero_da_el_esquema_de_los_modelos(base_nueva):
    _alembic(base_nueva, "upgrade", "head")
    _alembic(base_nueva, "check")  # falla si los modelos y las migraciones no coinciden

    assert set(inspect(base_nueva).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    extensiones = set(base_nueva.execute(text("SELECT extname FROM pg_extension")).scalars())
    assert {"uuid-ossp", "pgcrypto"} <= extensiones


def test_downgrade_hasta_el_principio_y_vuelta(base_nueva):
    _alembic(base_nueva, "upgrade", "head")
    _alembic(base_nueva, "downgrade", "base")
    assert inspect(base_nueva).get_table_names() == ["alembic_version"]

    _alembic(base_nueva, "upgrade", "head")
    _alembic(base_nueva, "check")


def test_una_base_de_antes_de_alembic_no_recibe_la_baseline(base_nueva):
    _base_de_antes_de_alembic(base_nueva)

    with pytest.raises(RuntimeError, match="alembic stamp 0001"):
        _alembic(base_nueva, "upgrade", "head")
    base_nueva.rollback()
    tablas = set(inspect(base_nueva).get_table_names())
    assert "core_schema_migrations" in tablas and "alembic_version" not in tablas


def test_adopcion_de_una_base_de_antes_de_alembic(base_nueva):
    _base_de_antes_de_alembic(base_nueva)
    with Session(bind=base_nueva) as sesion:  # secretos en claro, como antes de F02
        usuario = CoreDataFactory(sesion).usuario()
        usuario_id = usuario.id
        usuario.totp_backup_codes = json.dumps(["a1b2c3d4"])
        usuario.magic_link_token = "token-en-claro"
        sesion.add(
            ClienteOIDC(
                client_id="razorback", nombre="razorback", redirect_uris=[], scopes="openid", secreto_hash="hash"
            )
        )
        sesion.commit()

    _alembic(base_nueva, "stamp", "0001")
    _alembic(base_nueva, "upgrade", "head")
    _alembic(base_nueva, "check")

    assert not inspect(base_nueva).has_table("core_schema_migrations")
    constraints = set(base_nueva.execute(text("SELECT conname FROM pg_constraint")).scalars())
    assert {"uq_ticket_empresa_numero", "uq_pedido_empresa_numero", "innovacion_licencias_pkey"} <= constraints
    assert not {"soporte_tickets_numero_key", "admin_licencias_pkey"} & constraints
    defaults = (
        base_nueva.execute(
            text(
                "SELECT column_default FROM information_schema.columns WHERE (table_name, column_name) IN "
                "(('soporte_matriz_estado', 'updated_at'), ('starmiles_desafios', 'inscripcion_unica_por_empleado'))"
            )
        )
        .scalars()
        .all()
    )
    assert defaults == [None, None]
    codigos, link = base_nueva.execute(
        text("SELECT totp_backup_codes, magic_link_token FROM core_usuarios WHERE id = :id"), {"id": usuario_id}
    ).one()
    assert "a1b2c3d4" not in codigos and secretos.migrar(codigos) is None
    assert link == secretos.hash_magic_link("token-en-claro")
    # Con F21 y F22 ya hechos por create_all y la migración ad hoc (producción), la 0004 no recrea nada
    assert base_nueva.execute(text("SELECT client_id FROM core_oidc_clientes")).scalars().all() == ["razorback"]


def test_la_0004_agrega_el_secundario_y_copia_el_email_de_la_cuenta_a_sus_fichas(base_nueva):
    """Una base de antes de F22 (por ejemplo, la de desarrollo adoptada antes del merge de main): sin
    email_secundario ni tablas OIDC, con un email con espacios y una ficha con otro email."""
    _alembic(base_nueva, "upgrade", "head")
    with Session(bind=base_nueva) as sesion:
        datos = CoreDataFactory(sesion)
        empresa = datos.empresa()
        usuario = datos.usuario(email=f"ana.{uuid.uuid4().hex[:6]}@dicsys.com", dni=30_123_456)
        ficha = datos.empleado(empresa, dni=usuario.dni, email_corporativo="viejo@dicsys.com")
        usuario_id, ficha_id, email = usuario.id, ficha.id, usuario.email
        sesion.commit()
    _alembic(base_nueva, "downgrade", "0003")
    base_nueva.execute(text("UPDATE core_usuarios SET email = email || ' ' WHERE id = :id"), {"id": usuario_id})

    _alembic(base_nueva, "upgrade", "head")
    _alembic(base_nueva, "check")

    assert (
        base_nueva.execute(text("SELECT email FROM core_usuarios WHERE id = :id"), {"id": usuario_id}).scalar() == email
    )
    assert (
        base_nueva.execute(
            text("SELECT email_corporativo FROM nomina_empleados WHERE id = :id"), {"id": ficha_id}
        ).scalar()
        == email
    )


def test_check_no_ve_las_tablas_de_respaldo_a_mano(base_nueva):
    """Producción tiene recibos_*_bkp_20260722, respaldos hechos a mano: no son del esquema ni lo ensucian."""
    _alembic(base_nueva, "upgrade", "head")
    base_nueva.execute(text("CREATE TABLE recibos_logs_bkp_20260722 AS SELECT * FROM recibos_logs"))
    _alembic(base_nueva, "check")

    base_nueva.execute(text("CREATE TABLE recibos_logs_copia (id integer)"))  # una tabla cualquiera sí se ve
    with pytest.raises(Exception, match="recibos_logs_copia"):
        _alembic(base_nueva, "check")


def test_la_adopcion_se_corta_si_faltan_migraciones_ad_hoc(base_nueva):
    _base_de_antes_de_alembic(base_nueva, aplicadas=MIGRACIONES_AD_HOC[1:])
    _alembic(base_nueva, "stamp", "0001")

    with pytest.raises(RuntimeError, match=MIGRACIONES_AD_HOC[0]):
        _alembic(base_nueva, "upgrade", "head")
    base_nueva.rollback()
    assert inspect(base_nueva).has_table("core_schema_migrations")
