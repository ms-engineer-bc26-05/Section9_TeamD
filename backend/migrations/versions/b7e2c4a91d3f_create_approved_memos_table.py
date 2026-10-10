"""create approved_memos table

Revision ID: b7e2c4a91d3f
Revises: 4d4cb65c2eba
Create Date: 2026-10-10 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2c4a91d3f'
down_revision: Union[str, Sequence[str], None] = '4d4cb65c2eba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the approved_memos table (DB設計 approved_memos)."""
    op.create_table(
        "approved_memos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_consultation_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False),
        sa.Column("encryption_version", sa.String(32), nullable=False),
        sa.Column("key_version", sa.String(64), nullable=False),
        sa.Column("payload_version", sa.SmallInteger(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("save_consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approved_memos")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_approved_memos_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "user_id",
            "source_consultation_id",
            name=op.f("uq_approved_memos_user_id_source_consultation_id"),
        ),
        sa.CheckConstraint(
            "octet_length(encrypted_payload) > 0",
            name=op.f("ck_approved_memos_encrypted_payload_not_empty"),
        ),
        sa.CheckConstraint(
            "payload_version > 0",
            name=op.f("ck_approved_memos_payload_version_positive"),
        ),
    )
    op.create_index(
        op.f("ix_approved_memos_user_id_created_at_id"),
        "approved_memos",
        ["user_id", "created_at", "id"],
    )


def downgrade() -> None:
    """Drop the approved_memos table."""
    op.drop_index(op.f("ix_approved_memos_user_id_created_at_id"), table_name="approved_memos")
    op.drop_table("approved_memos")
