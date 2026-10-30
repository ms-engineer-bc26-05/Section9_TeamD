"""承認済み整理メモのテーブル定義（DB設計 approved_memos）。"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ApprovedMemo(Base):
    __tablename__ = "approved_memos"
    __table_args__ = (
        # 同じユーザーの同じ相談から、複数のメモを作らない
        UniqueConstraint("user_id", "source_consultation_id"),
        CheckConstraint("octet_length(encrypted_payload) > 0", name="encrypted_payload_not_empty"),
        CheckConstraint("payload_version > 0", name="payload_version_positive"),
        # メモ一覧の取得用
        Index(None, "user_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_consultation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_version: Mapped[str] = mapped_column(String(32), nullable=False)
    key_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    save_consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
