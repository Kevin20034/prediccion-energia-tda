"""Entorno de migraciones de Alembic.

Dos particularidades de este proyecto:

1. La URL se toma de ``settings.url_migraciones`` (el endpoint **directo** de
   Neon, sin `-pooler`). PgBouncer en modo transacción no lleva bien el DDL ni
   los *prepared statements* que emite Alembic.
2. Se activa ``compare_type`` para que ``alembic revision --autogenerate``
   detecte también los cambios de tipo de columna, no solo los de nombre.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Permite importar `src.*` cuando Alembic se ejecuta desde la raíz del proyecto.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import settings  # noqa: E402
from src.database.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inyecta la URL real en tiempo de ejecución (no está en alembic.ini).
config.set_main_option("sqlalchemy.url", settings.url_migraciones)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (`alembic upgrade head --sql`)."""
    context.configure(
        url=settings.url_migraciones,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones conectándose a la base de datos."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # una conexión por migración; sin pool
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
