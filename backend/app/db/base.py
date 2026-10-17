from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, MetaData, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# SQLite gives a column declared UUID NUMERIC affinity. Bare UUID hex values
# such as 12345678e999... can be coerced into float('inf') on INSERT and
# become unreadable as UUIDs. Use text affinity only for SQLite while keeping
# the native PostgreSQL UUID type and its existing API unchanged.
UUID_TEXT_SAFE = UUID(as_uuid=False).with_variant(String(36), "sqlite")


class UUIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(
        UUID_TEXT_SAFE,
        primary_key=True,
        default=lambda: str(uuid4()),
    )
