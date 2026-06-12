"""Alembic environment — reuses the app engine so the ADB wallet config stays in one place."""

from logging.config import fileConfig

from alembic import context

from app.core.database import Base, get_engine

# Import models so their tables are registered on Base.metadata for autogenerate.
from app.domains.users import models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


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
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
