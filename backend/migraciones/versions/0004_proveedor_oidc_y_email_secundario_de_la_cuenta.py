"""Proveedor OpenID Connect (F21) y email secundario de la cuenta (F22), que llegaron de main.

- Tablas core_oidc_clientes y core_oidc_codigos (backend/modules/oidc/models.py).
- core_usuarios.email_secundario. Al agregarla, como hacía la migración ad hoc usuarios_email_secundario_v1 de main: se
  recortan los espacios del email de las cuentas y se copia el email de cada cuenta a sus fichas vigentes (por DNI) si
  es de un dominio de la empresa de la ficha; si no, la ficha queda en null. Las fichas sin cuenta conservan el suyo.
- nomina_empleados.email_corporativo_secundario se va: solo existió en ramas de desarrollo de F22.

Una base de antes de Alembic que ya tenía F21 y F22 (producción desde el 2026-10-12) llega acá con todo eso: lo
crearon create_all y la migración ad hoc, y la adopción (0002) ya borró core_schema_migrations. Por eso cada paso mira
el esquema: lo que existe no se vuelve a crear y la copia a las fichas no se repite.

Revisión: 0004
Anterior: 0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DOMINIOS_POR_DEFECTO = "ARRAY['dicsys.ai', 'dicsys.com']"  # los de emails_corporativos.DOMINIOS_POR_DEFECTO

# El email de cada cuenta a sus fichas vigentes, si es de un dominio de la empresa de la ficha (sus dominios_email, una
# lista JSON; sin lista, los de por defecto). Si no lo es, la ficha queda en null.
COPIA_A_FICHAS = f"""
    WITH dominios AS (
        SELECT em.id,
               coalesce(
                   (SELECT array_agg(lower(trim(both '@ ' FROM d)))
                      FROM jsonb_array_elements_text(
                          CASE WHEN trim(em.dominios_email) ~ '^\\[.*\\]$' THEN em.dominios_email::jsonb
                               ELSE '[]'::jsonb END) d
                     WHERE trim(d) <> ''),
                   {DOMINIOS_POR_DEFECTO}) AS lista
          FROM core_empresas em
    )
    UPDATE nomina_empleados e
       SET email_corporativo = CASE
               WHEN split_part(lower(trim(u.email)), '@', 2) = ANY (d.lista) THEN lower(trim(u.email))
               ELSE NULL END
      FROM core_usuarios u, dominios d
     WHERE u.dni = e.dni AND u.deleted_at IS NULL AND e.deleted_at IS NULL AND d.id = e.empresa_id
"""


def _columnas(conexion, tabla: str) -> set[str]:
    return {columna["name"] for columna in sa.inspect(conexion).get_columns(tabla)}


def upgrade() -> None:
    conexion = op.get_bind()
    inspector = sa.inspect(conexion)

    if not inspector.has_table("core_oidc_clientes"):
        op.create_table(
            "core_oidc_clientes",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("client_id", sa.String(length=100), nullable=False),
            sa.Column("nombre", sa.String(length=150), nullable=False),
            sa.Column("redirect_uris", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("scopes", sa.String(length=255), nullable=False),
            sa.Column("secreto_hash", sa.String(length=100), nullable=False),
            sa.Column("secreto_nuevo_hash", sa.String(length=100), nullable=True),
            sa.Column("activo", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("client_id"),
        )
    if not inspector.has_table("core_oidc_codigos"):
        op.create_table(
            "core_oidc_codigos",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("codigo_hash", sa.String(length=64), nullable=False),
            sa.Column("cliente_id", sa.UUID(), nullable=False),
            sa.Column("usuario_id", sa.UUID(), nullable=False),
            sa.Column("redirect_uri", sa.String(length=500), nullable=False),
            sa.Column("scope", sa.String(length=255), nullable=False),
            sa.Column("nonce", sa.String(length=255), nullable=False),
            sa.Column("code_challenge", sa.String(length=128), nullable=False),
            sa.Column("expira_at", sa.DateTime(), nullable=False),
            sa.Column("usado_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["cliente_id"], ["core_oidc_clientes.id"]),
            sa.ForeignKeyConstraint(["usuario_id"], ["core_usuarios.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("codigo_hash"),
        )
        op.create_index(op.f("ix_core_oidc_codigos_expira_at"), "core_oidc_codigos", ["expira_at"], unique=False)

    if "email_secundario" not in _columnas(conexion, "core_usuarios"):
        op.add_column("core_usuarios", sa.Column("email_secundario", sa.String(length=255), nullable=True))
        op.execute("UPDATE core_usuarios SET email = trim(email) WHERE email <> trim(email)")
        op.execute(COPIA_A_FICHAS)

    if "email_corporativo_secundario" in _columnas(conexion, "nomina_empleados"):
        op.drop_column("nomina_empleados", "email_corporativo_secundario")


def downgrade() -> None:
    """Borra los clientes OIDC registrados y los secundarios de las cuentas: en producción no se baja de acá sin un
    backup. Los emails de las fichas quedan como estaban."""
    op.drop_column("core_usuarios", "email_secundario")
    op.drop_index(op.f("ix_core_oidc_codigos_expira_at"), table_name="core_oidc_codigos")
    op.drop_table("core_oidc_codigos")
    op.drop_table("core_oidc_clientes")
