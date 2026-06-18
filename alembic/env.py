"""Alembic environment — reuses the app engine so the ADB wallet config stays in one place."""

from logging.config import fileConfig

from alembic import context
from app.core.config import settings
from app.core.database import Base, get_engine

# Import models so their tables are registered on Base.metadata for autogenerate.
from app.domains.admin import models as admin_models  # noqa: F401
from app.domains.invitations import models as invitation_models  # noqa: F401
from app.domains.transactions import models as transaction_models  # noqa: F401
from app.domains.users import models as user_models  # noqa: F401
from app.domains.wallets import models as wallet_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# When the app owns a dedicated schema (ORACLE_SCHEMA), the alembic_version
# bookkeeping table lives there too. We connect as ADMIN and only reach that
# schema via ALTER SESSION SET CURRENT_SCHEMA, but Alembic's "does the version
# table exist?" check inspects the *connecting* user's schema by default — so
# without this it can't see FAMILY_BUDGET.alembic_version, tries to recreate it,
# and hits ORA-00955. Pinning version_table_schema makes the check (and writes)
# target the right schema. Empty → default (the connecting user's schema).
_version_table_schema = settings.oracle_schema or None


def include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    """Keep autogenerate focused on our own tables.

    ADB ships Oracle-managed tables (e.g. ``dbtools$execution_history`` from
    Database Actions / SQL Developer Web). Without this filter, autogenerate sees
    them as "removed" and emits a destructive ``drop_table`` against Oracle's own
    objects. Only reflect tables we actually define in our models.
    """
    if type_ == "table":
        return name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=str(get_engine().url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        version_table_schema=_version_table_schema,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
            version_table_schema=_version_table_schema,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
