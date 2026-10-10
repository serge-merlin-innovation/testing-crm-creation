from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ...infrastructure.database.models import TimestampMixin
from ...infrastructure.database.session import Base


class PicklistValue(Base, TimestampMixin):
    __tablename__ = "picklist_values"
    __table_args__ = (Index("ix_picklist_values_kind_code", "kind", "code", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label_en: Mapped[str] = mapped_column(String(200), nullable=False)
    label_fr: Mapped[str | None] = mapped_column(String(200), default=None)
    label_nl: Mapped[str | None] = mapped_column(String(200), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
