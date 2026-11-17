"""card wording: whose words the card is in

Revision ID: 0002_card_wording
Revises: 0001_initial
Create Date: 2026-11-12 09:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_card_wording"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stories",
        sa.Column("summary_kind", sa.String(length=16), server_default="composed",
                  nullable=False),
    )
    op.add_column(
        "stories", sa.Column("wording_source_name", sa.String(length=160), nullable=True)
    )
    op.create_check_constraint(
        "ck_stories_summary_kind", "stories", "summary_kind IN ('composed', 'excerpt')"
    )
    # A quotation with nobody's name on it is the one thing this column exists
    # to prevent, so the database refuses to hold one.
    op.create_check_constraint(
        "ck_stories_excerpt_is_credited",
        "stories",
        "summary_kind <> 'excerpt' OR wording_source_name IS NOT NULL OR summary = ''",
    )


def downgrade() -> None:
    op.drop_constraint("ck_stories_excerpt_is_credited", "stories", type_="check")
    op.drop_constraint("ck_stories_summary_kind", "stories", type_="check")
    op.drop_column("stories", "wording_source_name")
    op.drop_column("stories", "summary_kind")
