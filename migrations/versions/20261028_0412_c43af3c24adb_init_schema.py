"""init schema

Revision ID: c43af3c24adb
Revises:
Create Date: 2026-10-28 04:12:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c43af3c24adb'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tenants_slug'), 'tenants', ['slug'], unique=True)

    # Create projects table
    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=True),
        sa.Column('provider_config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_projects_slug'), 'projects', ['slug'], unique=False)
    op.create_index(op.f('ix_projects_tenant_id'), 'projects', ['tenant_id'], unique=False)
    op.create_unique_constraint('uq_projects_tenant_slug', 'projects', ['tenant_id', 'slug'])

    # Create repositories table
    op.create_table(
        'repositories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('default_branch', sa.String(length=100), server_default=sa.text("'main'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_repositories_external_id'), 'repositories', ['external_id'], unique=False)
    op.create_index(op.f('ix_repositories_project_id'), 'repositories', ['project_id'], unique=False)
    op.create_index(op.f('ix_repositories_tenant_id'), 'repositories', ['tenant_id'], unique=False)
    op.create_index('ix_repositories_project_provider', 'repositories', ['project_id', 'provider'], unique=False)
    op.create_index('ix_repositories_tenant_provider', 'repositories', ['tenant_id', 'provider'], unique=False)
    op.create_unique_constraint('uq_repositories_tenant_provider_external', 'repositories', ['tenant_id', 'provider', 'external_id'])


def downgrade() -> None:
    op.drop_constraint('uq_repositories_tenant_provider_external', 'repositories', type_='unique')
    op.drop_index('ix_repositories_tenant_provider', table_name='repositories')
    op.drop_index('ix_repositories_project_provider', table_name='repositories')
    op.drop_index(op.f('ix_repositories_tenant_id'), table_name='repositories')
    op.drop_index(op.f('ix_repositories_project_id'), table_name='repositories')
    op.drop_index(op.f('ix_repositories_external_id'), table_name='repositories')
    op.drop_table('repositories')
    op.drop_constraint('uq_projects_tenant_slug', 'projects', type_='unique')
    op.drop_index(op.f('ix_projects_tenant_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_slug'), table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_tenants_slug'), table_name='tenants')
    op.drop_table('tenants')