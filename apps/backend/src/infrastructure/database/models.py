import uuid as uuid_pkg
from datetime import UTC, datetime

from sqlalchemy import DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column
from sqlalchemy.types import TIMESTAMP


class UUIDMixin(MappedAsDataclass):
    uuid: Mapped[uuid_pkg.UUID] = mapped_column(
        UUID,
        primary_key=True,
        default=uuid_pkg.uuid4,
        server_default=text("gen_random_uuid()"),
        init=False,
    )


class TimestampMixin(MappedAsDataclass):
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
        init=False,
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
        nullable=True,
        init=False,
    )


class SoftDeleteMixin(MappedAsDataclass):
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        init=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        default=False,
        init=False,
    )
