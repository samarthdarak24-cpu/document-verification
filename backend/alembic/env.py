"""Alembic migration environment.

This file connects Alembic to the DocuTrace SQLAlchemy models:

* ``target_metadata`` comes from :class:`app.database.base.Base`, so autogenerate
  compares the *real* models against the database.
* The URL comes from the ``DATABASE_URL`` environment variable via
  :func:`app.core.config.get_settings`, so a test run can migrate a throw-away
  database by exporting a single variable.

Both offline (``--sql``) and online (default) modes are supported.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make ``backend/`` importable when Alembic is launched from another directory.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402  (after sys.path fix)
from app.database.base import Base  # noqa: E402
import app.models.models  # noqa: E402,F401  (registers every mapper)

# This is the Alembic Config object; ``config.config_file_name`` gives access to
# the values in ``alembic.ini``.
config = context.config

# Configure Python logging from the ini file (skipped under ``--sql`` less noisy
# setups where ``config_file_name`` is None).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata used by ``alembic revision --autogenerate``.
target_metadata = Base.metadata

# The URL comes from the environment/defaults, never from alembic.ini.
_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.DATABASE_URL)


def _configure_context(**kwargs):
    """Common context options shared by offline and online modes."""
    options = {
        "target_metadata": target_metadata,
        # Compare column *types* too, not just names/nullability.
        "compare_type": True,
        # Render CHECK/naming conventions as in the models.
        "literal_binds": False,
        # Needed for SQLite ALTER TABLE emulation (batch mode).
        "render_as_batch": True,
    }
    options.update(kwargs)
    return context.configure(**options)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode: emit SQL without a DBAPI connection."""
    url = config.get_main_option("sqlalchemy.url")
    _configure_context(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _configure_context(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
