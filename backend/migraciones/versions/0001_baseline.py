"""Baseline: el esquema completo de la app al adoptar Alembic (F04), con las extensiones de Postgres.

Es lo que dejaban create_all y las migraciones ad hoc que corría el backend al arrancar (las absorbe), generado con
`alembic revision --autogenerate` contra una base vacía y comparado con una base armada por el flujo anterior. En una
base vacía crea todo; una base de antes de Alembic ya lo tiene y se adopta con `alembic stamp 0001` (no corre esta
revisión): si se le aplica, se corta antes de tocar nada (docs/Migraciones.md).

Revisión: 0001
Anterior: ninguna
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("core_usuarios"):
        raise RuntimeError(
            "La base ya tiene el esquema de la app pero no el historial de Alembic: es de antes de F04. Se adopta con "
            "`alembic stamp 0001` y `alembic upgrade head` (docs/Migraciones.md, adopción); la baseline no se aplica."
        )
    # Antes en database/init.sql. uuid-ossp y pgcrypto son extensiones confiables: las crea el dueño de la base.
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "administracion_recibos_export",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("colaborador", sa.String(length=200), nullable=True),
        sa.Column("cliente", sa.String(length=100), nullable=True),
        sa.Column("apellido", sa.String(length=100), nullable=True),
        sa.Column("nombre", sa.String(length=100), nullable=True),
        sa.Column("dni", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_administracion_recibos_export_cliente"), "administracion_recibos_export", ["cliente"], unique=False
    )
    op.create_index(
        op.f("ix_administracion_recibos_export_dni"), "administracion_recibos_export", ["dni"], unique=False
    )
    op.create_table(
        "core_empresas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cuit", sa.String(length=13), nullable=False),
        sa.Column("razon_social", sa.String(length=200), nullable=False),
        sa.Column("nombre_fantasia", sa.String(length=200), nullable=True),
        sa.Column("responsabilidad_afip", sa.String(length=50), nullable=False),
        sa.Column("logo", sa.String(length=500), nullable=True),
        sa.Column("sitio_web", sa.String(length=255), nullable=True),
        sa.Column("telefono", sa.String(length=30), nullable=True),
        sa.Column("email_contacto", sa.String(length=255), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("dominios_email", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("nro_ingresos_brutos", sa.String(length=50), nullable=True),
        sa.Column("fecha_inicio_actividades", sa.Date(), nullable=True),
        sa.Column("nro_inscripcion_municipal", sa.String(length=50), nullable=True),
        sa.Column("regimen_retencion", sa.String(length=100), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_core_empresas_cuit"), "core_empresas", ["cuit"], unique=False)
    op.create_table(
        "core_envios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("origen", sa.String(length=100), nullable=False),
        sa.Column("canal", sa.String(length=20), nullable=False),
        sa.Column("destino", sa.String(length=255), nullable=False),
        sa.Column("asunto", sa.String(length=300), nullable=True),
        sa.Column("contenido", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("clave", sa.String(length=300), nullable=True),
        sa.Column("referencia", sa.String(length=120), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False),
        sa.Column("proximo_intento_at", sa.DateTime(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("enviado_at", sa.DateTime(), nullable=True),
        sa.Column("creada_at", sa.DateTime(), nullable=False),
        sa.Column("alerta_enviada", sa.Boolean(), nullable=False),
        sa.CheckConstraint("canal IN ('email', 'webex_personal', 'webex_room')", name="ck_core_envios_canal"),
        sa.CheckConstraint("estado IN ('pendiente', 'enviado', 'error')", name="ck_core_envios_estado"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_core_envios_pendientes", "core_envios", ["estado", "proximo_intento_at"], unique=False)
    op.create_index(
        "uq_core_envios_clave", "core_envios", ["clave"], unique=True, postgresql_where=sa.text("clave IS NOT NULL")
    )
    op.create_table(
        "core_grupos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )
    op.create_index(op.f("ix_core_grupos_deleted_at"), "core_grupos", ["deleted_at"], unique=False)
    op.create_table(
        "core_llm_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("modulo", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("periodo", sa.String(length=7), nullable=False),
        sa.Column("tokens_input", sa.Integer(), nullable=False),
        sa.Column("tokens_output", sa.Integer(), nullable=False),
        sa.Column("tokens_cache", sa.Integer(), nullable=False),
        sa.Column("tokens_total", sa.Integer(), nullable=False),
        sa.Column("costo_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("request_file", sa.String(length=500), nullable=True),
        sa.Column("response_file", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_mensaje", sa.Text(), nullable=True),
        sa.Column("latencia_ms", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_core_llm_requests_modulo"), "core_llm_requests", ["modulo"], unique=False)
    op.create_index(op.f("ix_core_llm_requests_periodo"), "core_llm_requests", ["periodo"], unique=False)
    op.create_table(
        "core_logs_sincronizacion",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("proceso_id", sa.UUID(), nullable=False),
        sa.Column("fecha_inicio", sa.DateTime(), nullable=False),
        sa.Column("fecha_fin", sa.DateTime(), nullable=True),
        sa.Column("resultado", sa.String(length=20), nullable=True),
        sa.Column("mensaje", sa.Text(), nullable=True),
        sa.Column("registros_procesados", sa.Integer(), nullable=True),
        sa.Column("registros_actualizados", sa.Integer(), nullable=True),
        sa.Column("registros_creados", sa.Integer(), nullable=True),
        sa.Column("registros_errores", sa.Integer(), nullable=True),
        sa.Column("detalle_errores", sa.Text(), nullable=True),
        sa.Column("ejecutado_por", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "core_menus",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("icono", sa.String(length=50), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_index(op.f("ix_core_menus_deleted_at"), "core_menus", ["deleted_at"], unique=False)
    op.create_table(
        "core_parametros",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("categoria", sa.String(length=100), nullable=False),
        sa.Column("subcategoria", sa.String(length=100), nullable=True),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("valor_default", sa.Text(), nullable=True),
        sa.Column("valor", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_core_parametros_categoria"), "core_parametros", ["categoria"], unique=False)
    op.create_index(op.f("ix_core_parametros_key"), "core_parametros", ["key"], unique=True)
    op.create_table(
        "core_procesos_sincronizacion",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("tipo_origen", sa.String(length=50), nullable=False),
        sa.Column("configuracion", sa.Text(), nullable=True),
        sa.Column("query_sql", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=True),
        sa.Column("ultima_ejecucion", sa.DateTime(), nullable=True),
        sa.Column("ultimo_resultado", sa.String(length=20), nullable=True),
        sa.Column("ultimo_mensaje", sa.Text(), nullable=True),
        sa.Column("registros_procesados", sa.Integer(), nullable=True),
        sa.Column("registros_actualizados", sa.Integer(), nullable=True),
        sa.Column("registros_creados", sa.Integer(), nullable=True),
        sa.Column("registros_errores", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_table(
        "core_tareas_corridas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tarea", sa.String(length=100), nullable=False),
        sa.Column("disparo", sa.String(length=20), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("solicitada_por", sa.String(length=255), nullable=True),
        sa.Column("creada_at", sa.DateTime(), nullable=False),
        sa.Column("inicio", sa.DateTime(), nullable=True),
        sa.Column("fin", sa.DateTime(), nullable=True),
        sa.Column("resultado", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("alerta_enviada", sa.Boolean(), nullable=False),
        sa.CheckConstraint("disparo IN ('programado', 'manual')", name="ck_core_tareas_corridas_disparo"),
        sa.CheckConstraint("estado IN ('pendiente', 'en_curso', 'ok', 'error')", name="ck_core_tareas_corridas_estado"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_core_tareas_corridas_estado", "core_tareas_corridas", ["estado"], unique=False)
    op.create_index("ix_core_tareas_corridas_tarea", "core_tareas_corridas", ["tarea", "creada_at"], unique=False)
    op.create_table(
        "core_usuarios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("apellido", sa.String(length=100), nullable=True),
        sa.Column("dni", sa.Integer(), nullable=True),
        sa.Column("telefono", sa.String(length=20), nullable=True),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("rol", sa.String(length=50), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("requiere_password_change", sa.Boolean(), nullable=False),
        sa.Column("magic_link_token", sa.String(length=255), nullable=True),
        sa.Column("magic_link_expires", sa.DateTime(), nullable=True),
        sa.Column("totp_secret", sa.String(length=255), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False),
        sa.Column("totp_required", sa.Boolean(), nullable=False),
        sa.Column("totp_backup_codes", sa.String(length=1000), nullable=True),
        sa.Column("ultimo_login", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_core_usuarios_deleted_at"), "core_usuarios", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_core_usuarios_dni"), "core_usuarios", ["dni"], unique=False)
    op.create_index(op.f("ix_core_usuarios_email"), "core_usuarios", ["email"], unique=False)
    op.create_index(op.f("ix_core_usuarios_magic_link_token"), "core_usuarios", ["magic_link_token"], unique=True)
    op.create_table(
        "core_webex_oauth_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("proposito", sa.String(length=50), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("refresh_expires_at", sa.DateTime(), nullable=True),
        sa.Column("account_email", sa.String(length=255), nullable=True),
        sa.Column("account_nombre", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposito"),
    )
    op.create_table(
        "nomina_categorias",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("departamento_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "nomina_departamentos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("manager_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "nomina_empleados",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("cuil", sa.BigInteger(), nullable=False),
        sa.Column("apellido", sa.String(length=100), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=True),
        sa.Column("dni", sa.Integer(), nullable=False),
        sa.Column("genero", sa.String(length=20), nullable=True),
        sa.Column("nacionalidad", sa.String(length=50), nullable=True),
        sa.Column("estado_civil", sa.String(length=30), nullable=True),
        sa.Column("nivel_estudio", sa.String(length=50), nullable=True),
        sa.Column("carrera_id", sa.UUID(), nullable=True),
        sa.Column("telefono_personal", sa.String(length=30), nullable=True),
        sa.Column("email_personal", sa.String(length=255), nullable=True),
        sa.Column("dir_laboral_pais", sa.String(length=50), nullable=True),
        sa.Column("dir_laboral_provincia", sa.String(length=50), nullable=True),
        sa.Column("dir_laboral_localidad", sa.String(length=100), nullable=True),
        sa.Column("dir_laboral_codigo_postal", sa.String(length=10), nullable=True),
        sa.Column("dir_laboral_barrio", sa.String(length=100), nullable=True),
        sa.Column("dir_laboral_calle", sa.String(length=150), nullable=True),
        sa.Column("dir_laboral_numero", sa.String(length=20), nullable=True),
        sa.Column("dir_laboral_piso", sa.String(length=10), nullable=True),
        sa.Column("dir_laboral_departamento", sa.String(length=10), nullable=True),
        sa.Column("usar_direccion_laboral", sa.Boolean(), nullable=True),
        sa.Column("dir_obsequios_pais", sa.String(length=50), nullable=True),
        sa.Column("dir_obsequios_provincia", sa.String(length=50), nullable=True),
        sa.Column("dir_obsequios_localidad", sa.String(length=100), nullable=True),
        sa.Column("dir_obsequios_codigo_postal", sa.String(length=10), nullable=True),
        sa.Column("dir_obsequios_barrio", sa.String(length=100), nullable=True),
        sa.Column("dir_obsequios_calle", sa.String(length=150), nullable=True),
        sa.Column("dir_obsequios_numero", sa.String(length=20), nullable=True),
        sa.Column("dir_obsequios_piso", sa.String(length=10), nullable=True),
        sa.Column("dir_obsequios_departamento", sa.String(length=10), nullable=True),
        sa.Column("preferencia_alimentaria", sa.String(length=100), nullable=True),
        sa.Column("instrucciones_entrega", sa.String(length=500), nullable=True),
        sa.Column("contacto_emergencia", sa.String(length=100), nullable=True),
        sa.Column("numero_emergencia", sa.String(length=30), nullable=True),
        sa.Column("parentesco", sa.String(length=50), nullable=True),
        sa.Column("fecha_alta", sa.Date(), nullable=True),
        sa.Column("fecha_baja", sa.Date(), nullable=True),
        sa.Column("motivo_baja", sa.String(length=100), nullable=True),
        sa.Column("email_corporativo", sa.String(length=255), nullable=True),
        sa.Column("departamento_id", sa.UUID(), nullable=True),
        sa.Column("perfil_id", sa.UUID(), nullable=True),
        sa.Column("hrbp_id", sa.UUID(), nullable=True),
        sa.Column("seniority", sa.String(length=50), nullable=True),
        sa.Column("puesto", sa.String(length=150), nullable=True),
        sa.Column("foto", sa.String(length=500), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["departamento_id"],
            ["nomina_departamentos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["hrbp_id"],
            ["nomina_empleados.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
        sa.UniqueConstraint("cuil"),
    )
    op.create_table(
        "nomina_perfiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("tipo", sa.String(length=50), nullable=True),
        sa.Column("categoria_id", sa.UUID(), nullable=True),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["categoria_id"],
            ["nomina_categorias.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "notificaciones_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=True),
        sa.Column("tipo", sa.String(length=50), nullable=False),
        sa.Column("fecha_evento", sa.Date(), nullable=False),
        sa.Column("empleado_id", sa.UUID(), nullable=True),
        sa.Column("empleado_nombre", sa.String(length=255), nullable=True),
        sa.Column("empleado_email", sa.String(length=255), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("contexto_presentacion", sa.Text(), nullable=True),
        sa.Column("mensaje_generado", sa.Text(), nullable=True),
        sa.Column("llm_request_id", sa.String(length=64), nullable=True),
        sa.Column("webex_message_id", sa.String(length=255), nullable=True),
        sa.Column("error_detalle", sa.Text(), nullable=True),
        sa.Column("enviado_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notificaciones_log_empleado_id"), "notificaciones_log", ["empleado_id"], unique=False)
    op.create_index(op.f("ix_notificaciones_log_estado"), "notificaciones_log", ["estado"], unique=False)
    op.create_index(op.f("ix_notificaciones_log_fecha_evento"), "notificaciones_log", ["fecha_evento"], unique=False)
    op.create_index(op.f("ix_notificaciones_log_tipo"), "notificaciones_log", ["tipo"], unique=False)
    op.create_table(
        "soporte_pedidos_estados",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("clave", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clave"),
    )
    op.create_table(
        "soporte_tickets_estados",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("clave", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clave"),
    )
    op.create_table(
        "admin_categorias_cliente",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre"),
    )
    op.create_table(
        "admin_clientes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("cuit", sa.String(length=13), nullable=False),
        sa.Column("razon_social", sa.String(length=200), nullable=False),
        sa.Column("nombre_fantasia", sa.String(length=200), nullable=True),
        sa.Column("responsabilidad_afip", sa.String(length=50), nullable=False),
        sa.Column("sitio_web", sa.String(length=255), nullable=True),
        sa.Column("logo", sa.String(length=500), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("nro_ingresos_brutos", sa.String(length=50), nullable=True),
        sa.Column("fecha_inicio_actividades", sa.Date(), nullable=True),
        sa.Column("nro_inscripcion_municipal", sa.String(length=50), nullable=True),
        sa.Column("regimen_retencion", sa.String(length=100), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_admin_clientes_cuit"), "admin_clientes", ["cuit"], unique=False)
    op.create_table(
        "core_auditoria_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("fecha_hora", sa.DateTime(), nullable=False),
        sa.Column("modulo", sa.String(length=100), nullable=False),
        sa.Column("ruta", sa.String(length=500), nullable=False),
        sa.Column("metodo", sa.String(length=10), nullable=False),
        sa.Column("email_usuario", sa.String(length=255), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auditoria_log_empresa_email", "core_auditoria_log", ["empresa_id", "email_usuario"], unique=False
    )
    op.create_index("ix_auditoria_log_empresa_fecha", "core_auditoria_log", ["empresa_id", "fecha_hora"], unique=False)
    op.create_index("ix_auditoria_log_empresa_modulo", "core_auditoria_log", ["empresa_id", "modulo"], unique=False)
    op.create_index(op.f("ix_core_auditoria_log_email_usuario"), "core_auditoria_log", ["email_usuario"], unique=False)
    op.create_index(op.f("ix_core_auditoria_log_empresa_id"), "core_auditoria_log", ["empresa_id"], unique=False)
    op.create_index(op.f("ix_core_auditoria_log_fecha_hora"), "core_auditoria_log", ["fecha_hora"], unique=False)
    op.create_index(op.f("ix_core_auditoria_log_modulo"), "core_auditoria_log", ["modulo"], unique=False)
    op.create_table(
        "core_empresa_domicilios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("calle", sa.String(length=200), nullable=False),
        sa.Column("numero", sa.String(length=20), nullable=True),
        sa.Column("piso", sa.String(length=20), nullable=True),
        sa.Column("departamento", sa.String(length=20), nullable=True),
        sa.Column("localidad", sa.String(length=100), nullable=False),
        sa.Column("provincia", sa.String(length=100), nullable=False),
        sa.Column("pais", sa.String(length=100), nullable=False),
        sa.Column("codigo_postal", sa.String(length=10), nullable=True),
        sa.Column("vigente", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "core_grupo_departamento",
        sa.Column("grupo_id", sa.UUID(), nullable=False),
        sa.Column("departamento_id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["departamento_id"],
            ["nomina_departamentos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["grupo_id"],
            ["core_grupos.id"],
        ),
        sa.PrimaryKeyConstraint("grupo_id", "departamento_id", "empresa_id"),
    )
    op.create_table(
        "core_grupo_menu",
        sa.Column("grupo_id", sa.UUID(), nullable=False),
        sa.Column("menu_id", sa.UUID(), nullable=False),
        sa.Column("puede_ver", sa.Boolean(), nullable=True),
        sa.Column("puede_acceder", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["grupo_id"],
            ["core_grupos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["menu_id"],
            ["core_menus.id"],
        ),
        sa.PrimaryKeyConstraint("grupo_id", "menu_id"),
    )
    op.create_table(
        "core_menu_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("menu_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("icono", sa.String(length=50), nullable=True),
        sa.Column("ruta", sa.String(length=200), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["menu_id"],
            ["core_menus.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_core_menu_items_deleted_at"), "core_menu_items", ["deleted_at"], unique=False)
    op.create_table(
        "core_notificaciones_internas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("enlace", sa.String(length=500), nullable=True),
        sa.Column("origen", sa.String(length=100), nullable=True),
        sa.Column("leida_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["core_usuarios.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notificaciones_internas_usuario_bandeja_v2",
        "core_notificaciones_internas",
        ["empresa_id", "usuario_id", "deleted_at", "leida_at", "created_at"],
        unique=False,
    )
    op.create_table(
        "core_permisos_modulo",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("grupo_id", sa.UUID(), nullable=False),
        sa.Column("modulo", sa.String(length=100), nullable=False),
        sa.Column("tiene_acceso", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["grupo_id"],
            ["core_grupos.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_core_permisos_modulo_deleted_at"), "core_permisos_modulo", ["deleted_at"], unique=False)
    op.create_table(
        "core_usuario_empresa",
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["core_usuarios.id"],
        ),
        sa.PrimaryKeyConstraint("usuario_id", "empresa_id"),
    )
    op.create_table(
        "core_usuario_grupo",
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("grupo_id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["grupo_id"],
            ["core_grupos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["core_usuarios.id"],
        ),
        sa.PrimaryKeyConstraint("usuario_id", "grupo_id", "empresa_id"),
    )
    op.create_table(
        "hrbp_item_tipos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("stock_actual", sa.Integer(), nullable=False),
        sa.Column("stock_minimo", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "innovacion_certificaciones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("empleado_id", sa.UUID(), nullable=False),
        sa.Column("tipo_certificacion", sa.String(length=30), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("repo_presentacion", sa.String(length=500), nullable=True),
        sa.Column("repo_demo", sa.String(length=500), nullable=True),
        sa.Column("tematica", sa.String(length=200), nullable=True),
        sa.Column("tecnologias", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("fecha_presentacion", sa.Date(), nullable=True),
        sa.Column("fecha_aprobacion", sa.Date(), nullable=True),
        sa.Column("cert_noncode_origen", sa.String(length=20), nullable=True),
        sa.Column("cert_noncode_imagen", sa.String(length=500), nullable=True),
        sa.Column("cert_noncode_fecha", sa.Date(), nullable=True),
        sa.Column("cert_noncode_plan", sa.String(length=500), nullable=True),
        sa.Column("cert_n8n_origen", sa.String(length=20), nullable=True),
        sa.Column("cert_n8n_imagen", sa.String(length=500), nullable=True),
        sa.Column("cert_n8n_fecha", sa.Date(), nullable=True),
        sa.Column("cert_n8n_plan", sa.String(length=500), nullable=True),
        sa.Column("cert_ruta1_imagen", sa.String(length=500), nullable=True),
        sa.Column("cert_ruta1_fecha", sa.Date(), nullable=True),
        sa.Column("cert_ruta2_imagen", sa.String(length=500), nullable=True),
        sa.Column("cert_ruta2_fecha", sa.Date(), nullable=True),
        sa.Column("cert_ruta3_imagen", sa.String(length=500), nullable=True),
        sa.Column("cert_ruta3_fecha", sa.Date(), nullable=True),
        sa.Column("progreso_completados", sa.String(length=10), nullable=True),
        sa.Column("porcentaje_avance", sa.String(length=10), nullable=True),
        sa.Column("fecha_registro", sa.DateTime(), nullable=True),
        sa.Column("fecha_en_progreso", sa.DateTime(), nullable=True),
        sa.Column("fecha_en_presentacion", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "innovacion_eventos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("duenio", sa.String(length=100), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "innovacion_proveedores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("nombre_normalizado", sa.String(length=150), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_proveedor_empresa_nombre",
        "innovacion_proveedores",
        ["empresa_id", "nombre_normalizado"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "nomina_carreras",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "operaciones_equipos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("cliente_id", sa.UUID(), nullable=True),
        sa.Column("lider_id", sa.UUID(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["lider_id"],
            ["nomina_empleados.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "proveedores_configuracion",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("sheet_url", sa.String(length=500), nullable=True),
        sa.Column("sheet_hoja", sa.String(length=100), nullable=False),
        sa.Column("recordar_cada_dias", sa.SmallInteger(), nullable=True),
        sa.Column("aviso_apertura", sa.Boolean(), nullable=False),
        sa.Column("aviso_previo_cierre", sa.Boolean(), nullable=False),
        sa.Column("hora_envio", sa.Time(), server_default=sa.text("'09:00'"), nullable=False),
        sa.Column("canal_email", sa.Boolean(), nullable=False),
        sa.Column("email_cc", sa.Text(), nullable=True),
        sa.Column("canal_webex_personal", sa.Boolean(), nullable=False),
        sa.Column("canal_webex_canal", sa.Boolean(), nullable=False),
        sa.Column("webex_room_id", sa.String(length=255), nullable=True),
        sa.Column("auto_generar", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("auto_inicio_dia", sa.SmallInteger(), nullable=True),
        sa.Column("auto_inicio_mes", sa.SmallInteger(), nullable=True),
        sa.Column("auto_fin_dia", sa.SmallInteger(), nullable=True),
        sa.Column("auto_fin_mes", sa.SmallInteger(), nullable=True),
        sa.Column("auto_ultimo_periodo", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "NOT auto_generar OR (auto_inicio_dia IS NOT NULL AND auto_inicio_mes IS NOT NULL AND auto_fin_dia IS NOT NULL AND auto_fin_mes IS NOT NULL)",
            name="ck_proveedores_config_auto",
        ),
        sa.CheckConstraint("NOT canal_webex_canal OR webex_room_id IS NOT NULL", name="ck_proveedores_config_room"),
        sa.CheckConstraint(
            "auto_inicio_dia BETWEEN 1 AND 31 AND auto_fin_dia BETWEEN 1 AND 31 AND auto_inicio_mes BETWEEN 1 AND 12 AND auto_fin_mes BETWEEN 1 AND 12",
            name="ck_proveedores_config_auto_rangos",
        ),
        sa.CheckConstraint("recordar_cada_dias IN (1, 2)", name="ck_proveedores_config_recordar"),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id"),
    )
    op.create_table(
        "proveedores_evaluaciones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("periodo", sa.String(length=20), nullable=False),
        sa.Column("fecha_apertura", sa.Date(), nullable=False),
        sa.Column("fecha_cierre", sa.Date(), nullable=False),
        sa.Column("reemplazada_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("fecha_cierre >= fecha_apertura", name="ck_proveedores_evaluacion_fechas"),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_proveedores_evaluacion_periodo",
        "proveedores_evaluaciones",
        ["empresa_id", "periodo"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_proveedores_evaluacion_vigente",
        "proveedores_evaluaciones",
        ["empresa_id"],
        unique=True,
        postgresql_where=sa.text("reemplazada_at IS NULL AND deleted_at IS NULL"),
    )
    op.create_table(
        "proveedores_proveedores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("razon_social", sa.String(length=200), nullable=True),
        sa.Column("cuit", sa.String(length=13), nullable=True),
        sa.Column("responsabilidad_afip", sa.String(length=50), nullable=True),
        sa.Column("nro_ingresos_brutos", sa.String(length=50), nullable=True),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("referente_empleado_id", sa.UUID(), nullable=True),
        sa.Column("servicio_provisto", sa.Text(), nullable=True),
        sa.Column("tipo_informacion", sa.Text(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("telefono_whatsapp", sa.String(length=20), nullable=True),
        sa.Column("pagina_web", sa.String(length=500), nullable=True),
        sa.Column("acuerdo_servicio", sa.String(length=5), nullable=True),
        sa.Column("politica_nda", sa.Text(), nullable=True),
        sa.Column("politica_nda_archivo", sa.String(length=500), nullable=True),
        sa.Column("politica_nda_archivo_nombre", sa.String(length=255), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("acuerdo_servicio IN ('Si', 'No')", name="ck_proveedores_acuerdo"),
        sa.CheckConstraint(
            "responsabilidad_afip IN ('Responsable Inscripto', 'Sujeto Exento', 'Consumidor Final', 'Responsable Monotributo', 'Proveedor del Exterior', 'Sujeto No Categorizado')",
            name="ck_proveedores_iva",
        ),
        sa.CheckConstraint("tipo IN ('proveedor', 'herramienta', 'sin_clasificar')", name="ck_proveedores_tipo"),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["referente_empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proveedores_referente", "proveedores_proveedores", ["referente_empleado_id"], unique=False)
    op.create_index(
        "uq_proveedores_empresa_nombre",
        "proveedores_proveedores",
        ["empresa_id", sa.literal_column("lower(btrim(nombre))")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "recibos_lotes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("periodo", sa.String(length=7), nullable=False),
        sa.Column("tipo_liquidacion", sa.String(length=50), nullable=False),
        sa.Column("estado", sa.String(length=30), nullable=False),
        sa.Column("archivo_original", sa.String(length=500), nullable=False),
        sa.Column("archivo_nombre", sa.String(length=255), nullable=False),
        sa.Column("total_paginas", sa.Integer(), nullable=True),
        sa.Column("total_recibos", sa.Integer(), nullable=True),
        sa.Column("total_errores", sa.Integer(), nullable=True),
        sa.Column("errores_detalle", sa.JSON(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_activos_marcas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "nombre", name="uq_marca_empresa_nombre"),
    )
    op.create_table(
        "soporte_activos_tipos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("clave", sa.String(length=100), nullable=False),
        sa.Column("requiere_especificaciones", sa.Boolean(), nullable=False),
        sa.Column("frecuencia_mantenimiento_meses", sa.Integer(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "clave", name="uq_tipo_activo_empresa_clave"),
        sa.UniqueConstraint("empresa_id", "nombre", name="uq_tipo_activo_empresa_nombre"),
    )
    op.create_table(
        "soporte_categorias",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre_display", sa.String(length=100), nullable=False),
        sa.Column("nombre_normalizado", sa.String(length=100), nullable=False),
        sa.Column("tipo_ticket_asociado", sa.String(length=20), nullable=False),
        sa.Column("departamento_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["departamento_id"],
            ["nomina_departamentos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_matriz_estado",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("pantalla", sa.String(length=50), nullable=True),
        sa.Column("teclado", sa.String(length=50), nullable=True),
        sa.Column("bateria", sa.String(length=50), nullable=True),
        sa.Column("carcasa_superior", sa.String(length=50), nullable=True),
        sa.Column("carcasa_inferior", sa.String(length=50), nullable=True),
        sa.Column("touchpad", sa.String(length=50), nullable=True),
        sa.Column("puertos", sa.String(length=50), nullable=True),
        sa.Column("cargador", sa.String(length=50), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_sistemas_disponibles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("clave", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=10), nullable=False),
        sa.Column("clave_alta_ref", sa.String(length=100), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "clave", name="uq_sistema_disponible_empresa_clave"),
    )
    op.create_table(
        "starmiles_categorias",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("icono", sa.String(length=50), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "starmiles_contenido_cms",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=True),
        sa.Column("imagen_url", sa.String(length=500), nullable=True),
        sa.Column("empleado_id", sa.UUID(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=True),
        sa.Column("visible", sa.Boolean(), nullable=True),
        sa.Column("fecha_publicacion", sa.DateTime(), nullable=True),
        sa.Column("fecha_expiracion", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "starmiles_empleados",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("empleado_id", sa.UUID(), nullable=False),
        sa.Column("millas_historicas", sa.Integer(), nullable=False),
        sa.Column("millas_disponibles", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empleado_id"),
    )
    op.create_table(
        "starmiles_items_canje",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("star_miles_costo", sa.Integer(), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=True),
        sa.Column("imagen_url", sa.String(length=500), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "admin_cliente_categoria",
        sa.Column("cliente_id", sa.UUID(), nullable=False),
        sa.Column("categoria_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["categoria_id"],
            ["admin_categorias_cliente.id"],
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"],
            ["admin_clientes.id"],
        ),
        sa.PrimaryKeyConstraint("cliente_id", "categoria_id"),
    )
    op.create_table(
        "admin_cliente_domicilios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("cliente_id", sa.UUID(), nullable=False),
        sa.Column("calle", sa.String(length=200), nullable=False),
        sa.Column("numero", sa.String(length=20), nullable=True),
        sa.Column("piso", sa.String(length=20), nullable=True),
        sa.Column("departamento", sa.String(length=20), nullable=True),
        sa.Column("localidad", sa.String(length=100), nullable=False),
        sa.Column("provincia", sa.String(length=100), nullable=False),
        sa.Column("pais", sa.String(length=100), nullable=False),
        sa.Column("codigo_postal", sa.String(length=10), nullable=True),
        sa.Column("vigente", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["cliente_id"],
            ["admin_clientes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "hrbp_entregas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("item_tipo_id", sa.UUID(), nullable=False),
        sa.Column("empleado_id", sa.UUID(), nullable=False),
        sa.Column("hrbp_usuario_id", sa.UUID(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("fecha_entrega", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["hrbp_usuario_id"],
            ["core_usuarios.id"],
        ),
        sa.ForeignKeyConstraint(
            ["item_tipo_id"],
            ["hrbp_item_tipos.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "innovacion_evento_asistencia",
        sa.Column("evento_id", sa.UUID(), nullable=False),
        sa.Column("empleado_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evento_id"],
            ["innovacion_eventos.id"],
        ),
        sa.PrimaryKeyConstraint("evento_id", "empleado_id"),
    )
    op.create_table(
        "innovacion_herramientas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("nombre_normalizado", sa.String(length=150), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=True),
        sa.Column("costo_referencia", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("moneda", sa.String(length=3), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"],
            ["innovacion_proveedores.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_herramienta_empresa_nombre",
        "innovacion_herramientas",
        ["empresa_id", "nombre_normalizado"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "operaciones_equipo_integrantes",
        sa.Column("equipo_id", sa.UUID(), nullable=False),
        sa.Column("empleado_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["equipo_id"],
            ["operaciones_equipos.id"],
        ),
        sa.PrimaryKeyConstraint("equipo_id", "empleado_id"),
    )
    op.create_table(
        "proveedores_auditoria",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("fecha_hora", sa.DateTime(), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=True),
        sa.Column("usuario_email", sa.String(length=255), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("entidad", sa.String(length=20), nullable=False),
        sa.Column("entidad_id", sa.UUID(), nullable=False),
        sa.Column("evaluacion_id", sa.UUID(), nullable=True),
        sa.Column("accion", sa.String(length=30), nullable=False),
        sa.Column("antes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("despues", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "entidad IN ('proveedor', 'contacto', 'oficina', 'documento', 'configuracion', 'evaluacion', 'item', 'aviso')",
            name="ck_proveedores_auditoria_entidad",
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evaluacion_id"],
            ["proveedores_evaluaciones.id"],
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["core_usuarios.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_proveedores_auditoria_entidad",
        "proveedores_auditoria",
        ["entidad", "entidad_id", "fecha_hora"],
        unique=False,
    )
    op.create_index(
        "ix_proveedores_auditoria_evaluacion", "proveedores_auditoria", ["evaluacion_id", "fecha_hora"], unique=False
    )
    op.create_table(
        "proveedores_avisos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("evaluacion_id", sa.UUID(), nullable=False),
        sa.Column("fecha_hora", sa.DateTime(), nullable=False),
        sa.Column("fecha_local", sa.Date(), nullable=False),
        sa.Column("motivo", sa.String(length=15), nullable=False),
        sa.Column("canal", sa.String(length=15), nullable=False),
        sa.Column("empleado_id", sa.UUID(), nullable=True),
        sa.Column("destino", sa.String(length=255), nullable=False),
        sa.Column("cc", sa.Text(), nullable=True),
        sa.Column("pendientes", sa.Integer(), nullable=False),
        sa.Column("enviado", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("enviado_por", sa.UUID(), nullable=True),
        sa.CheckConstraint("canal IN ('email', 'webex_personal', 'webex_canal')", name="ck_proveedores_aviso_canal"),
        sa.CheckConstraint(
            "motivo IN ('apertura', 'recordatorio', 'previo_cierre', 'manual')", name="ck_proveedores_aviso_motivo"
        ),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["enviado_por"],
            ["core_usuarios.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evaluacion_id"],
            ["proveedores_evaluaciones.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_proveedores_aviso_diario",
        "proveedores_avisos",
        [
            "evaluacion_id",
            "motivo",
            "canal",
            sa.literal_column("coalesce(empleado_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "fecha_local",
        ],
        unique=True,
        postgresql_where=sa.text("enviado AND motivo <> 'manual'"),
    )
    op.create_table(
        "proveedores_documentos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("clave", sa.String(length=500), nullable=False),
        sa.Column("tipo_mime", sa.String(length=100), nullable=False),
        sa.Column("tamano", sa.Integer(), nullable=False),
        sa.Column("miniatura_clave", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"],
            ["proveedores_proveedores.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proveedores_documentos_proveedor", "proveedores_documentos", ["proveedor_id"], unique=False)
    op.create_table(
        "proveedores_evaluacion_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("evaluacion_id", sa.UUID(), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=False),
        sa.Column("evaluador_empleado_id", sa.UUID(), nullable=True),
        sa.Column("incidentes", sa.String(length=5), nullable=True),
        sa.Column("mal_manejo", sa.String(length=5), nullable=True),
        sa.Column("evidencia_incidentes", sa.Text(), nullable=True),
        sa.Column("evidencia_mal_manejo", sa.Text(), nullable=True),
        sa.Column(
            "con_hallazgo",
            sa.Boolean(),
            sa.Computed("COALESCE(incidentes = 'Si', FALSE) OR COALESCE(mal_manejo = 'Si', FALSE)", persisted=True),
            nullable=True,
        ),
        sa.Column("evaluado_at", sa.DateTime(), nullable=True),
        sa.Column("evaluado_por", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("incidentes IN ('Si', 'No', 'N/A')", name="ck_proveedores_item_incidentes"),
        sa.CheckConstraint("mal_manejo IN ('Si', 'No')", name="ck_proveedores_item_mal_manejo"),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evaluacion_id"],
            ["proveedores_evaluaciones.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evaluado_por"],
            ["core_usuarios.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evaluador_empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"],
            ["proveedores_proveedores.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_proveedores_item_evaluador",
        "proveedores_evaluacion_items",
        ["evaluacion_id", "evaluador_empleado_id"],
        unique=False,
    )
    op.create_index(
        "uq_proveedores_item_evaluacion_proveedor",
        "proveedores_evaluacion_items",
        ["evaluacion_id", "proveedor_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "proveedores_importaciones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("evaluacion_id", sa.UUID(), nullable=False),
        sa.Column("creada_at", sa.DateTime(), nullable=False),
        sa.Column("creada_por", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["creada_por"],
            ["core_usuarios.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evaluacion_id"],
            ["proveedores_evaluaciones.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        prefixes=["UNLOGGED"],
    )
    op.create_table(
        "proveedores_oficinas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=False),
        sa.Column("nombre_oficina", sa.String(length=100), nullable=True),
        sa.Column("calle", sa.String(length=200), nullable=False),
        sa.Column("numero", sa.String(length=20), nullable=True),
        sa.Column("piso", sa.String(length=20), nullable=True),
        sa.Column("departamento", sa.String(length=20), nullable=True),
        sa.Column("localidad", sa.String(length=100), nullable=False),
        sa.Column("provincia", sa.String(length=100), nullable=True),
        sa.Column("pais", sa.String(length=100), nullable=False),
        sa.Column("codigo_postal", sa.String(length=10), nullable=True),
        sa.Column("es_legal", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"],
            ["proveedores_proveedores.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proveedores_oficinas_proveedor", "proveedores_oficinas", ["proveedor_id"], unique=False)
    op.create_index(
        "uq_proveedores_oficina_legal",
        "proveedores_oficinas",
        ["proveedor_id"],
        unique=True,
        postgresql_where=sa.text("es_legal AND deleted_at IS NULL"),
    )
    op.create_table(
        "recibos_recibos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("lote_id", sa.UUID(), nullable=False),
        sa.Column("empleado_id", sa.UUID(), nullable=True),
        sa.Column("cuil_extraido", sa.BigInteger(), nullable=False),
        sa.Column("archivo_original", sa.String(length=500), nullable=False),
        sa.Column("archivo_duplicado", sa.String(length=500), nullable=True),
        sa.Column("archivo_firmado", sa.String(length=500), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("pagina_original", sa.Integer(), nullable=False),
        sa.Column("pagina_duplicado", sa.Integer(), nullable=True),
        sa.Column("fecha_firma", sa.DateTime(), nullable=True),
        sa.Column("ip_firma", sa.String(length=45), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["lote_id"],
            ["recibos_lotes.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_activos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("clase_activo", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("tipo_id", sa.UUID(), nullable=False),
        sa.Column("marca_id", sa.UUID(), nullable=True),
        sa.Column("modelo", sa.String(length=100), nullable=True),
        sa.Column("numero_serie", sa.String(length=100), nullable=True),
        sa.Column("numero_inventario", sa.String(length=50), nullable=True),
        sa.Column("estado", sa.String(length=50), nullable=True),
        sa.Column("asignado_id", sa.UUID(), nullable=True),
        sa.Column("fecha_asignacion", sa.DateTime(), nullable=True),
        sa.Column("fecha_compra", sa.DateTime(), nullable=True),
        sa.Column("fecha_fin_garantia", sa.DateTime(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("fecha_ultimo_mantenimiento", sa.DateTime(), nullable=True),
        sa.Column("matriz_estado_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["asignado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["marca_id"],
            ["soporte_activos_marcas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["matriz_estado_id"],
            ["soporte_matriz_estado.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tipo_id"],
            ["soporte_activos_tipos.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "numero_inventario", name="uq_activo_empresa_inventario"),
        sa.UniqueConstraint("empresa_id", "numero_serie", name="uq_activo_empresa_serie"),
    )
    op.create_table(
        "soporte_insumos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("stock_actual", sa.Integer(), nullable=True),
        sa.Column("stock_minimo", sa.Integer(), nullable=True),
        sa.Column("unidad_medida", sa.String(length=20), nullable=True),
        sa.Column("categoria_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["categoria_id"],
            ["soporte_categorias.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_subcategorias",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("categoria_id", sa.UUID(), nullable=False),
        sa.Column("nombre_display", sa.String(length=100), nullable=False),
        sa.Column("nombre_normalizado", sa.String(length=100), nullable=False),
        sa.Column("tipo_ticket_asociado", sa.String(length=20), nullable=False),
        sa.Column("departamento_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["categoria_id"],
            ["soporte_categorias.id"],
        ),
        sa.ForeignKeyConstraint(
            ["departamento_id"],
            ["nomina_departamentos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "starmiles_canjes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("empleado_id", sa.UUID(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("star_miles_total", sa.Integer(), nullable=False),
        sa.Column("mercadolibre_url", sa.String(length=500), nullable=True),
        sa.Column("mercadolibre_precio", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("fecha_solicitud", sa.DateTime(), nullable=False),
        sa.Column("fecha_aprobacion", sa.DateTime(), nullable=True),
        sa.Column("fecha_entrega", sa.DateTime(), nullable=True),
        sa.Column("fecha_rechazo", sa.DateTime(), nullable=True),
        sa.Column("aprobador_id", sa.UUID(), nullable=True),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["aprobador_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["starmiles_items_canje.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "starmiles_desafios",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("categoria_id", sa.UUID(), nullable=True),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("alcance", sa.String(length=255), nullable=True),
        sa.Column("star_miles", sa.Integer(), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=True),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=True),
        sa.Column("inscripcion_unica_por_empleado", sa.Boolean(), nullable=False),
        sa.Column("imagen_url", sa.String(length=500), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["categoria_id"],
            ["starmiles_categorias.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "innovacion_licencias",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("herramienta_id", sa.UUID(), nullable=False),
        sa.Column("nro_pedido_compra", sa.String(length=50), nullable=True),
        sa.Column("costo_mensual", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("moneda", sa.String(length=3), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False),
        sa.Column("empleado_id", sa.UUID(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["herramienta_id"],
            ["innovacion_herramientas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "proveedores_contactos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=False),
        sa.Column("oficina_id", sa.UUID(), nullable=True),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("apellido", sa.String(length=100), nullable=True),
        sa.Column("cargo", sa.String(length=150), nullable=True),
        sa.Column("telefono", sa.String(length=30), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("es_principal", sa.Boolean(), nullable=False),
        sa.Column("notas", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["oficina_id"],
            ["proveedores_oficinas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"],
            ["proveedores_proveedores.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proveedores_contactos_proveedor", "proveedores_contactos", ["proveedor_id"], unique=False)
    op.create_index(
        "uq_proveedores_contacto_principal",
        "proveedores_contactos",
        ["proveedor_id"],
        unique=True,
        postgresql_where=sa.text("es_principal AND deleted_at IS NULL"),
    )
    op.create_table(
        "proveedores_importacion_filas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("importacion_id", sa.UUID(), nullable=False),
        sa.Column("fila_sheet", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("referente_sheet", sa.String(length=200), nullable=True),
        sa.Column("accion", sa.String(length=20), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=True),
        sa.Column("referente_anterior_id", sa.UUID(), nullable=True),
        sa.Column("referente_nuevo_id", sa.UUID(), nullable=True),
        sa.Column("servicio_provisto", sa.Text(), nullable=True),
        sa.Column("tipo_informacion", sa.Text(), nullable=True),
        sa.Column("acuerdo_servicio", sa.String(length=5), nullable=True),
        sa.Column("politica_nda", sa.Text(), nullable=True),
        sa.Column("confirmar", sa.Boolean(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "accion IN ('alta', 'sin_cambios', 'cambio_referente', 'rechazada')",
            name="ck_proveedores_importacion_accion",
        ),
        sa.ForeignKeyConstraint(["importacion_id"], ["proveedores_importaciones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        prefixes=["UNLOGGED"],
    )
    op.create_index(
        "ix_proveedores_importacion_filas", "proveedores_importacion_filas", ["importacion_id"], unique=False
    )
    op.create_table(
        "recibos_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("recibo_id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("accion", sa.String(length=50), nullable=False),
        sa.Column("usuario_email", sa.String(length=255), nullable=True),
        sa.Column("usuario_nombre", sa.String(length=200), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("detalle", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["recibo_id"],
            ["recibos_recibos.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_activos_especificaciones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("procesador", sa.String(length=150), nullable=True),
        sa.Column("memoria", sa.String(length=50), nullable=True),
        sa.Column("disco_principal", sa.String(length=100), nullable=True),
        sa.Column("disco_secundario", sa.String(length=100), nullable=True),
        sa.Column("mac_ethernet", sa.String(length=100), nullable=True),
        sa.Column("mac_wifi", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["soporte_activos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_mantenimiento_evento",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("activo_id", sa.UUID(), nullable=True),
        sa.Column("asignado_id", sa.UUID(), nullable=True),
        sa.Column("fecha_ejecucion", sa.DateTime(), nullable=True),
        sa.Column("estado_anterior", sa.String(length=20), nullable=True),
        sa.Column("estado_nuevo", sa.String(length=20), nullable=True),
        sa.Column("fecha_hora", sa.DateTime(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["activo_id"],
            ["soporte_activos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["asignado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_tickets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("tipo_ticket", sa.String(length=20), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("estado_id", sa.UUID(), nullable=False),
        sa.Column("prioridad", sa.String(length=50), nullable=False),
        sa.Column("subcategoria_id", sa.UUID(), nullable=False),
        sa.Column("es_falla", sa.Boolean(), nullable=False),
        sa.Column("solicitante_id", sa.UUID(), nullable=False),
        sa.Column("asignado_id", sa.UUID(), nullable=True),
        sa.Column("resolucion", sa.Text(), nullable=True),
        sa.Column("fecha_inicio", sa.DateTime(), nullable=True),
        sa.Column("fecha_resolucion", sa.DateTime(), nullable=True),
        sa.Column("fecha_cierre", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["asignado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["estado_id"],
            ["soporte_tickets_estados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["solicitante_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["subcategoria_id"],
            ["soporte_subcategorias.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "numero", name="uq_ticket_empresa_numero"),
    )
    op.create_table(
        "starmiles_inscripciones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("desafio_id", sa.UUID(), nullable=False),
        sa.Column("empleado_id", sa.UUID(), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("fecha_solicitud", sa.DateTime(), nullable=False),
        sa.Column("fecha_aprobacion", sa.DateTime(), nullable=True),
        sa.Column("fecha_finalizacion", sa.DateTime(), nullable=True),
        sa.Column("fecha_rechazo", sa.DateTime(), nullable=True),
        sa.Column("aprobador_id", sa.UUID(), nullable=True),
        sa.Column("comentario_solicitud", sa.Text(), nullable=True),
        sa.Column("comentario_aprobador", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["aprobador_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["desafio_id"],
            ["starmiles_desafios.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_starmiles_inscripciones_desafio_empleado_estado",
        "starmiles_inscripciones",
        ["empresa_id", "desafio_id", "empleado_id", "estado"],
        unique=False,
    )
    op.create_table(
        "soporte_pedidos_compra",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("numero", sa.String(length=50), nullable=False),
        sa.Column("tipo_pedido", sa.String(length=20), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("monto_estimado", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("monto_final", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("estado_id", sa.UUID(), nullable=True),
        sa.Column("fecha_solicitud", sa.DateTime(), nullable=True),
        sa.Column("fecha_recepcion", sa.DateTime(), nullable=True),
        sa.Column("solicitante_id", sa.UUID(), nullable=True),
        sa.Column("ticket_id", sa.UUID(), nullable=True),
        sa.Column("insumo_id", sa.UUID(), nullable=True),
        sa.Column("cantidad_solicitada", sa.Integer(), nullable=True),
        sa.Column("cantidad_recibida", sa.Integer(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("requiere_doble_aprobacion", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["estado_id"],
            ["soporte_pedidos_estados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["insumo_id"],
            ["soporte_insumos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["solicitante_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["soporte_tickets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "numero", name="uq_pedido_empresa_numero"),
    )
    op.create_table(
        "soporte_ticket_checklist_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("sistema_id", sa.UUID(), nullable=True),
        sa.Column("item_clave", sa.String(length=100), nullable=False),
        sa.Column("item_label", sa.String(length=255), nullable=False),
        sa.Column("completado", sa.Boolean(), nullable=False),
        sa.Column("completado_por", sa.String(length=255), nullable=True),
        sa.Column("completado_at", sa.DateTime(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["sistema_id"],
            ["soporte_sistemas_disponibles.id"],
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["soporte_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_tickets_alta_baja",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("colaborador_id", sa.UUID(), nullable=False),
        sa.Column("tipo_operacion", sa.String(length=10), nullable=False),
        sa.Column("entrega_kit_bienvenida", sa.Boolean(), nullable=True),
        sa.Column("activo_id", sa.UUID(), nullable=True),
        sa.Column("matriz_estado_id", sa.UUID(), nullable=True),
        sa.Column("modalidad_trabajo", sa.String(length=30), nullable=True),
        sa.Column("requiere_nextcloud", sa.Boolean(), nullable=True),
        sa.Column("listas_correo", sa.Text(), nullable=True),
        sa.Column("necesita_computadora", sa.Boolean(), nullable=True),
        sa.Column("gama_computadora", sa.String(length=50), nullable=True),
        sa.Column("cliente_servicio", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["activo_id"],
            ["soporte_activos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(["id"], ["soporte_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["matriz_estado_id"],
            ["soporte_matriz_estado.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_tickets_mantenimiento",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("activo_id", sa.UUID(), nullable=False),
        sa.Column("mantenimiento_id", sa.UUID(), nullable=True),
        sa.Column("detalle_tecnico", sa.Text(), nullable=True),
        sa.Column("is_preventivo", sa.Boolean(), nullable=True),
        sa.Column("fecha_programada", sa.DateTime(), nullable=True),
        sa.Column("se_realizo", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["activo_id"],
            ["soporte_activos.id"],
        ),
        sa.ForeignKeyConstraint(["id"], ["soporte_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["mantenimiento_id"],
            ["soporte_mantenimiento_evento.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_tickets_reparacion",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("activo_id", sa.UUID(), nullable=False),
        sa.Column("diagnostico", sa.Text(), nullable=True),
        sa.Column("solucion", sa.Text(), nullable=True),
        sa.Column("costo_estimado", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("costo_total_final", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("matriz_entrada_id", sa.UUID(), nullable=True),
        sa.Column("matriz_salida_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["activo_id"],
            ["soporte_activos.id"],
        ),
        sa.ForeignKeyConstraint(["id"], ["soporte_tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["matriz_entrada_id"],
            ["soporte_matriz_estado.id"],
        ),
        sa.ForeignKeyConstraint(
            ["matriz_salida_id"],
            ["soporte_matriz_estado.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_historial_activo",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("activo_id", sa.UUID(), nullable=True),
        sa.Column("colaborador_id", sa.UUID(), nullable=True),
        sa.Column("responsable_id", sa.UUID(), nullable=True),
        sa.Column("fecha_hora", sa.DateTime(), nullable=True),
        sa.Column("tipo_evento", sa.String(length=50), nullable=True),
        sa.Column("notas_adicionales", sa.Text(), nullable=True),
        sa.Column("matriz_estado_id", sa.UUID(), nullable=True),
        sa.Column("pedido_compra_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["activo_id"],
            ["soporte_activos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["colaborador_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["matriz_estado_id"],
            ["soporte_matriz_estado.id"],
        ),
        sa.ForeignKeyConstraint(
            ["pedido_compra_id"],
            ["soporte_pedidos_compra.id"],
        ),
        sa.ForeignKeyConstraint(
            ["responsable_id"],
            ["nomina_empleados.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_movimientos_insumos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("insumo_id", sa.UUID(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("activo_id", sa.UUID(), nullable=True),
        sa.Column("empleado_id", sa.UUID(), nullable=True),
        sa.Column("empleado_asignador_id", sa.UUID(), nullable=True),
        sa.Column("pedido_compra_id", sa.UUID(), nullable=True),
        sa.Column("motivo", sa.String(length=255), nullable=True),
        sa.Column("fecha_movimiento", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["activo_id"],
            ["soporte_activos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empleado_asignador_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empleado_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["insumo_id"],
            ["soporte_insumos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["pedido_compra_id"],
            ["soporte_pedidos_compra.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_pedidos_aprobaciones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("pedido_id", sa.UUID(), nullable=True),
        sa.Column("departamento_id", sa.UUID(), nullable=True),
        sa.Column("aprobador_id", sa.UUID(), nullable=True),
        sa.Column("estado", sa.String(length=50), nullable=True),
        sa.Column("fecha_decision", sa.DateTime(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("orden_aprobacion", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["aprobador_id"],
            ["nomina_empleados.id"],
        ),
        sa.ForeignKeyConstraint(
            ["departamento_id"],
            ["nomina_departamentos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["pedido_id"],
            ["soporte_pedidos_compra.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_pedidos_presupuestos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("pedido_id", sa.UUID(), nullable=True),
        sa.Column("proveedor", sa.String(length=200), nullable=True),
        sa.Column("url_archivo", sa.String(length=500), nullable=True),
        sa.Column("articulo_descripcion", sa.Text(), nullable=True),
        sa.Column("monto", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("es_seleccionado", sa.Boolean(), nullable=True),
        sa.Column("es_obligatorio", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["pedido_id"],
            ["soporte_pedidos_compra.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_evidencias",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("tipo", sa.String(length=50), nullable=False),
        sa.Column("categoria", sa.String(length=50), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=True),
        sa.Column("activo_id", sa.UUID(), nullable=True),
        sa.Column("historial_id", sa.UUID(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["activo_id"],
            ["soporte_activos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["historial_id"],
            ["soporte_historial_activo.id"],
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["soporte_tickets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soporte_tickets_insumos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("insumo_id", sa.UUID(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=True),
        sa.Column("costo_unitario", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("generar_pedido_compra", sa.Boolean(), nullable=True),
        sa.Column("movimiento_insumo_id", sa.UUID(), nullable=True),
        sa.Column("pedido_compra_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["empresa_id"],
            ["core_empresas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["insumo_id"],
            ["soporte_insumos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["movimiento_insumo_id"],
            ["soporte_movimientos_insumos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["pedido_compra_id"],
            ["soporte_pedidos_compra.id"],
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["soporte_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Ciclo de nómina (categorías → departamentos → empleados → perfiles → categorías) y carrera del empleado (el orden
    # de autogenerate crea nomina_carreras después): estas FKs van al final, con el nombre que les pone Postgres
    op.create_foreign_key(
        "nomina_categorias_departamento_id_fkey",
        "nomina_categorias",
        "nomina_departamentos",
        ["departamento_id"],
        ["id"],
    )
    op.create_foreign_key(
        "nomina_departamentos_manager_id_fkey", "nomina_departamentos", "nomina_empleados", ["manager_id"], ["id"]
    )
    op.create_foreign_key(
        "nomina_empleados_perfil_id_fkey", "nomina_empleados", "nomina_perfiles", ["perfil_id"], ["id"]
    )
    op.create_foreign_key(
        "nomina_empleados_carrera_id_fkey", "nomina_empleados", "nomina_carreras", ["carrera_id"], ["id"]
    )


def downgrade() -> None:
    """Borra todas las tablas; las extensiones quedan (otras bases del servidor o herramientas pueden usarlas)."""
    op.drop_constraint("nomina_categorias_departamento_id_fkey", "nomina_categorias", type_="foreignkey")
    op.drop_constraint("nomina_departamentos_manager_id_fkey", "nomina_departamentos", type_="foreignkey")
    op.drop_constraint("nomina_empleados_perfil_id_fkey", "nomina_empleados", type_="foreignkey")
    op.drop_constraint("nomina_empleados_carrera_id_fkey", "nomina_empleados", type_="foreignkey")
    op.drop_table("soporte_tickets_insumos")
    op.drop_table("soporte_evidencias")
    op.drop_table("soporte_pedidos_presupuestos")
    op.drop_table("soporte_pedidos_aprobaciones")
    op.drop_table("soporte_movimientos_insumos")
    op.drop_table("soporte_historial_activo")
    op.drop_table("soporte_tickets_reparacion")
    op.drop_table("soporte_tickets_mantenimiento")
    op.drop_table("soporte_tickets_alta_baja")
    op.drop_table("soporte_ticket_checklist_items")
    op.drop_table("soporte_pedidos_compra")
    op.drop_index("ix_starmiles_inscripciones_desafio_empleado_estado", table_name="starmiles_inscripciones")
    op.drop_table("starmiles_inscripciones")
    op.drop_table("soporte_tickets")
    op.drop_table("soporte_mantenimiento_evento")
    op.drop_table("soporte_activos_especificaciones")
    op.drop_table("recibos_logs")
    op.drop_index("ix_proveedores_importacion_filas", table_name="proveedores_importacion_filas")
    op.drop_table("proveedores_importacion_filas")
    op.drop_index(
        "uq_proveedores_contacto_principal",
        table_name="proveedores_contactos",
        postgresql_where=sa.text("es_principal AND deleted_at IS NULL"),
    )
    op.drop_index("ix_proveedores_contactos_proveedor", table_name="proveedores_contactos")
    op.drop_table("proveedores_contactos")
    op.drop_table("innovacion_licencias")
    op.drop_table("starmiles_desafios")
    op.drop_table("starmiles_canjes")
    op.drop_table("soporte_subcategorias")
    op.drop_table("soporte_insumos")
    op.drop_table("soporte_activos")
    op.drop_table("recibos_recibos")
    op.drop_index(
        "uq_proveedores_oficina_legal",
        table_name="proveedores_oficinas",
        postgresql_where=sa.text("es_legal AND deleted_at IS NULL"),
    )
    op.drop_index("ix_proveedores_oficinas_proveedor", table_name="proveedores_oficinas")
    op.drop_table("proveedores_oficinas")
    op.drop_table("proveedores_importaciones")
    op.drop_index(
        "uq_proveedores_item_evaluacion_proveedor",
        table_name="proveedores_evaluacion_items",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index("ix_proveedores_item_evaluador", table_name="proveedores_evaluacion_items")
    op.drop_table("proveedores_evaluacion_items")
    op.drop_index("ix_proveedores_documentos_proveedor", table_name="proveedores_documentos")
    op.drop_table("proveedores_documentos")
    op.drop_index(
        "uq_proveedores_aviso_diario",
        table_name="proveedores_avisos",
        postgresql_where=sa.text("enviado AND motivo <> 'manual'"),
    )
    op.drop_table("proveedores_avisos")
    op.drop_index("ix_proveedores_auditoria_evaluacion", table_name="proveedores_auditoria")
    op.drop_index("ix_proveedores_auditoria_entidad", table_name="proveedores_auditoria")
    op.drop_table("proveedores_auditoria")
    op.drop_table("operaciones_equipo_integrantes")
    op.drop_index(
        "uq_herramienta_empresa_nombre",
        table_name="innovacion_herramientas",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("innovacion_herramientas")
    op.drop_table("innovacion_evento_asistencia")
    op.drop_table("hrbp_entregas")
    op.drop_table("admin_cliente_domicilios")
    op.drop_table("admin_cliente_categoria")
    op.drop_table("starmiles_items_canje")
    op.drop_table("starmiles_empleados")
    op.drop_table("starmiles_contenido_cms")
    op.drop_table("starmiles_categorias")
    op.drop_table("soporte_sistemas_disponibles")
    op.drop_table("soporte_matriz_estado")
    op.drop_table("soporte_categorias")
    op.drop_table("soporte_activos_tipos")
    op.drop_table("soporte_activos_marcas")
    op.drop_table("recibos_lotes")
    op.drop_index(
        "uq_proveedores_empresa_nombre",
        table_name="proveedores_proveedores",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index("ix_proveedores_referente", table_name="proveedores_proveedores")
    op.drop_table("proveedores_proveedores")
    op.drop_index(
        "uq_proveedores_evaluacion_vigente",
        table_name="proveedores_evaluaciones",
        postgresql_where=sa.text("reemplazada_at IS NULL AND deleted_at IS NULL"),
    )
    op.drop_index(
        "uq_proveedores_evaluacion_periodo",
        table_name="proveedores_evaluaciones",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("proveedores_evaluaciones")
    op.drop_table("proveedores_configuracion")
    op.drop_table("operaciones_equipos")
    op.drop_table("nomina_carreras")
    op.drop_index(
        "uq_proveedor_empresa_nombre",
        table_name="innovacion_proveedores",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("innovacion_proveedores")
    op.drop_table("innovacion_eventos")
    op.drop_table("innovacion_certificaciones")
    op.drop_table("hrbp_item_tipos")
    op.drop_table("core_usuario_grupo")
    op.drop_table("core_usuario_empresa")
    op.drop_index(op.f("ix_core_permisos_modulo_deleted_at"), table_name="core_permisos_modulo")
    op.drop_table("core_permisos_modulo")
    op.drop_index("ix_notificaciones_internas_usuario_bandeja_v2", table_name="core_notificaciones_internas")
    op.drop_table("core_notificaciones_internas")
    op.drop_index(op.f("ix_core_menu_items_deleted_at"), table_name="core_menu_items")
    op.drop_table("core_menu_items")
    op.drop_table("core_grupo_menu")
    op.drop_table("core_grupo_departamento")
    op.drop_table("core_empresa_domicilios")
    op.drop_index(op.f("ix_core_auditoria_log_modulo"), table_name="core_auditoria_log")
    op.drop_index(op.f("ix_core_auditoria_log_fecha_hora"), table_name="core_auditoria_log")
    op.drop_index(op.f("ix_core_auditoria_log_empresa_id"), table_name="core_auditoria_log")
    op.drop_index(op.f("ix_core_auditoria_log_email_usuario"), table_name="core_auditoria_log")
    op.drop_index("ix_auditoria_log_empresa_modulo", table_name="core_auditoria_log")
    op.drop_index("ix_auditoria_log_empresa_fecha", table_name="core_auditoria_log")
    op.drop_index("ix_auditoria_log_empresa_email", table_name="core_auditoria_log")
    op.drop_table("core_auditoria_log")
    op.drop_index(op.f("ix_admin_clientes_cuit"), table_name="admin_clientes")
    op.drop_table("admin_clientes")
    op.drop_table("admin_categorias_cliente")
    op.drop_table("soporte_tickets_estados")
    op.drop_table("soporte_pedidos_estados")
    op.drop_index(op.f("ix_notificaciones_log_tipo"), table_name="notificaciones_log")
    op.drop_index(op.f("ix_notificaciones_log_fecha_evento"), table_name="notificaciones_log")
    op.drop_index(op.f("ix_notificaciones_log_estado"), table_name="notificaciones_log")
    op.drop_index(op.f("ix_notificaciones_log_empleado_id"), table_name="notificaciones_log")
    op.drop_table("notificaciones_log")
    op.drop_table("nomina_perfiles")
    op.drop_table("nomina_empleados")
    op.drop_table("nomina_departamentos")
    op.drop_table("nomina_categorias")
    op.drop_table("core_webex_oauth_tokens")
    op.drop_index(op.f("ix_core_usuarios_magic_link_token"), table_name="core_usuarios")
    op.drop_index(op.f("ix_core_usuarios_email"), table_name="core_usuarios")
    op.drop_index(op.f("ix_core_usuarios_dni"), table_name="core_usuarios")
    op.drop_index(op.f("ix_core_usuarios_deleted_at"), table_name="core_usuarios")
    op.drop_table("core_usuarios")
    op.drop_index("ix_core_tareas_corridas_tarea", table_name="core_tareas_corridas")
    op.drop_index("ix_core_tareas_corridas_estado", table_name="core_tareas_corridas")
    op.drop_table("core_tareas_corridas")
    op.drop_table("core_procesos_sincronizacion")
    op.drop_index(op.f("ix_core_parametros_key"), table_name="core_parametros")
    op.drop_index(op.f("ix_core_parametros_categoria"), table_name="core_parametros")
    op.drop_table("core_parametros")
    op.drop_index(op.f("ix_core_menus_deleted_at"), table_name="core_menus")
    op.drop_table("core_menus")
    op.drop_table("core_logs_sincronizacion")
    op.drop_index(op.f("ix_core_llm_requests_periodo"), table_name="core_llm_requests")
    op.drop_index(op.f("ix_core_llm_requests_modulo"), table_name="core_llm_requests")
    op.drop_table("core_llm_requests")
    op.drop_index(op.f("ix_core_grupos_deleted_at"), table_name="core_grupos")
    op.drop_table("core_grupos")
    op.drop_index("uq_core_envios_clave", table_name="core_envios", postgresql_where=sa.text("clave IS NOT NULL"))
    op.drop_index("ix_core_envios_pendientes", table_name="core_envios")
    op.drop_table("core_envios")
    op.drop_index(op.f("ix_core_empresas_cuit"), table_name="core_empresas")
    op.drop_table("core_empresas")
    op.drop_index(op.f("ix_administracion_recibos_export_dni"), table_name="administracion_recibos_export")
    op.drop_index(op.f("ix_administracion_recibos_export_cliente"), table_name="administracion_recibos_export")
    op.drop_table("administracion_recibos_export")
