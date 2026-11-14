"""Initial baseline schema covering core jobs, users, cache, and SaaS multi-tenant tables.

Revision ID: 0001_initial_baseline
Revises: 
Create Date: 2026-11-14 14:24:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Jobs table
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True, index=True),
        sa.Column('progress', sa.Integer(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('meeting_type', sa.String(length=50), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True),
        sa.Column('token_cost_usd', sa.Float(), nullable=True),
        sa.Column('tenant_id', sa.String(length=36), nullable=True, index=True),
        sa.Column('file_path', sa.String(length=500), nullable=True),
    )

    # 2. Cache Entries
    op.create_table(
        'cache_entries',
        sa.Column('query_hash', sa.String(length=64), primary_key=True),
        sa.Column('response', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True, index=True),
    )

    # 3. Users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('username', sa.String(length=100), unique=True, nullable=False, index=True),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # 4. Organizations
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('tier', sa.String(length=50), nullable=True),
        sa.Column('monthly_audio_quota_seconds', sa.Float(), nullable=True),
        sa.Column('consumed_audio_seconds', sa.Float(), nullable=True),
        sa.Column('total_token_cost_usd', sa.Float(), nullable=True),
        sa.Column('raw_audio_retention_days', sa.Integer(), nullable=True),
        sa.Column('certificate_retention_years', sa.Integer(), nullable=True),
        sa.Column('stripe_customer_id', sa.String(length=255), nullable=True, index=True),
        sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True, index=True),
        sa.Column('current_period_end', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # 5. Org Memberships
    op.create_table(
        'org_memberships',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), nullable=False, index=True),
        sa.Column('user_id', sa.String(length=36), nullable=False, index=True),
        sa.Column('role', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # 6. Audit Trail Events (SOC2 / HIPAA Ledger)
    op.create_table(
        'audit_trail_events',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), nullable=False, index=True),
        sa.Column('user_id', sa.String(length=36), nullable=True, index=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_id', sa.String(length=255), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table('audit_trail_events')
    op.drop_table('org_memberships')
    op.drop_table('organizations')
    op.drop_table('users')
    op.drop_table('cache_entries')
    op.drop_table('jobs')

