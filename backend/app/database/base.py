"""SQLAlchemy 2.0 declarative base.

Every DocuTrace ORM model inherits from :class:`Base`. The 2.0 style
(``Mapped[...]`` annotated attributes + ``mapped_column``) is used throughout so
the models are type-checker friendly and the ``declarative_base`` factory is the
only legacy-free entry point.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all DocuTrace ORM models.

    Provides the ``metadata`` collection used by ``create_all`` (startup) and by
    Alembic's ``target_metadata`` (migrations), keeping schema creation and
    migration generation in sync.
    """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        primary_keys = ", ".join(
            f"{column.name}={getattr(self, column.name, None)!r}"
            for column in self.__table__.primary_key.columns
        )
        return f"<{type(self).__name__}({primary_keys})>"
