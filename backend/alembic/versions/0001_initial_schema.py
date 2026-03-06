"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ativa fuzzy search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # jurisdictions
    op.create_table(
        "jurisdictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("uf", sa.String(2)),
        sa.Column("ibge_code", sa.String(7), unique=True),
        sa.Column("state_id", sa.Integer(), sa.ForeignKey("jurisdictions.id")),
        sa.Column("search_aliases", postgresql.ARRAY(sa.String())),
        sa.Column("data_confidence", sa.String(10), server_default="unknown"),
        sa.Column("last_researched", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_jurisdictions_level", "jurisdictions", ["level"])
    op.create_index("idx_jurisdictions_uf", "jurisdictions", ["uf"])
    op.create_index(
        "idx_jurisdictions_name_trgm",
        "jurisdictions",
        [sa.text("lower(name) gin_trgm_ops")],
        postgresql_using="gin",
    )

    # rpv_ceilings
    op.create_table(
        "rpv_ceilings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jurisdiction_id", sa.Integer(), sa.ForeignKey("jurisdictions.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date()),
        sa.Column("ceiling_type", sa.String(20), nullable=False),
        sa.Column("ceiling_value", sa.Numeric(15, 2)),
        sa.Column("ceiling_description", sa.Text(), nullable=False),
        sa.Column("legislation_name", sa.Text(), nullable=False),
        sa.Column("legislation_url", sa.Text()),
        sa.Column("legislation_description", sa.Text()),
        sa.Column("uses_federal_fallback", sa.Boolean(), server_default="false"),
        sa.Column("confidence", sa.String(10), server_default="unknown"),
        sa.Column("ai_research_notes", sa.Text()),
        sa.Column("flagged_for_review", sa.Boolean(), server_default="false"),
        sa.Column("flag_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_ceilings_jurisdiction", "rpv_ceilings", ["jurisdiction_id"])
    op.create_index("idx_ceilings_valid_from", "rpv_ceilings", ["valid_from"])

    # research_log
    op.create_table(
        "research_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jurisdiction_id", sa.Integer(), sa.ForeignKey("jurisdictions.id")),
        sa.Column("search_query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("ai_model_used", sa.String(50)),
        sa.Column("tokens_used", sa.Integer()),
        sa.Column("estimated_cost_usd", sa.Numeric(8, 6)),
        sa.Column("raw_ai_response", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("triggered_by", sa.String(20), server_default="user_query"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    # minimum_salary_history
    op.create_table(
        "minimum_salary_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date()),
        sa.Column("value_brl", sa.Numeric(10, 2), nullable=False),
        sa.Column("legislation", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("minimum_salary_history")
    op.drop_table("research_log")
    op.drop_table("rpv_ceilings")
    op.drop_table("jurisdictions")
