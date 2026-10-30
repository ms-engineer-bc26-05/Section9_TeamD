"""アプリ内ユーザーのテーブル定義。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    Uuid,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'deleting')",
            name="status_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    firebase_uid: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active"
    )
    has_seen_notice: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
