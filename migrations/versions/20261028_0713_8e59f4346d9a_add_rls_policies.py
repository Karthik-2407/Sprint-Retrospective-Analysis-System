"""add_rls_policies

Revision ID: 8e59f4346d9a
Revises: 4bee8e11bd3a
Create Date: 2026-10-28 07:13:30.262855+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8e59f4346d9a'
down_revision: Union[str, None] = '4bee8e11bd3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Define the app.tenant_id setting using SET (outside transaction via autocommit_block)
    # This defines the setting for the current session and sets a default
    with op.get_context().autocommit_block():
        op.execute("SET app.tenant_id = '00000000-0000-0000-0000-000000000000'")
    
    # Enable RLS on all tenant-isolated tables
    tables_with_rls = [
        'projects',
        'repositories',
        'provider_connections',
        'commits',
        'deployments',
        'incidents',
        'ingestion_runs',
        'pull_requests',
        'metric_snapshots',
        'raw_events',
        'quarantined_events',
        'incident_deployment_links',
    ]
    
    for table in tables_with_rls:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        
        # Create policy for SELECT, INSERT, UPDATE, DELETE
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = current_setting('app.tenant_id')::uuid)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)
        """)


def downgrade() -> None:
    tables_with_rls = [
        'projects',
        'repositories',
        'provider_connections',
        'commits',
        'deployments',
        'incidents',
        'ingestion_runs',
        'pull_requests',
        'metric_snapshots',
        'raw_events',
        'quarantined_events',
        'incident_deployment_links',
    ]
    
    for table in tables_with_rls:
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}')
        op.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')
    
    with op.get_context().autocommit_block():
        op.execute("RESET app.tenant_id")
