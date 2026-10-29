"""Integration tests for snapshot recomputation pipeline.

Tests the full pipeline: raw events → normalized tables → metric snapshots.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dora_platform.db.models import (
    Commit as DBCommit,
)
from dora_platform.db.models import (
    Deployment as DBDeployment,
)
from dora_platform.db.models import (
    Incident as DBIncident,
)
from dora_platform.db.models import (
    IncidentDeploymentLink as DBIncidentDeploymentLink,
)
from dora_platform.db.models import (
    MetricSnapshot,
    Project,
    PullRequest as DBPullRequest,
)
from dora_platform.db.models import (
    Repository,
)
from dora_platform.db.models import (
    Tenant,
)
from dora_platform.db.tenant import set_tenant_context
from dora_platform.ingestion.snapshotter import Snapshotter, recompute_all_snapshots
from dora_platform.linking.engine import LinkingEngine


class TestSnapshotRecompute:
    """Test full snapshot recomputation pipeline."""

    @pytest.fixture
    async def test_tenant(self, db_session: AsyncSession) -> Tenant:
        """Create a test tenant."""
        tenant = Tenant(
            name="Test Tenant",
            slug=f"test-tenant-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(tenant)
        await db_session.flush()
        await db_session.refresh(tenant)
        return tenant

    @pytest.fixture
    async def test_project(self, db_session: AsyncSession, test_tenant: Tenant) -> Project:
        """Create a test project with tenant context."""
        await set_tenant_context(db_session, test_tenant.id)
        project = Project(
            tenant_id=test_tenant.id,
            name="Test Project",
            slug=f"test-project-{uuid.uuid4().hex[:8]}",
            provider="github",
        )
        db_session.add(project)
        await db_session.flush()
        await db_session.refresh(project)
        return project

    @pytest.fixture
    async def test_repo(self, db_session: AsyncSession, test_tenant: Tenant, test_project: Project) -> Repository:
        """Create a test repository."""
        await set_tenant_context(db_session, test_tenant.id)
        repo = Repository(
            tenant_id=test_tenant.id,
            project_id=test_project.id,
            name=f"test-repo-{uuid.uuid4().hex[:8]}",
            provider="github",
            external_id="12345",
            url="https://github.com/test/test-repo",
        )
        db_session.add(repo)
        await db_session.flush()
        await db_session.refresh(repo)
        return repo

    async def test_snapshotter_creates_all_metric_snapshots(
        self, db_session: AsyncSession, test_tenant: Tenant, test_repo: Repository
    ):
        """Test that Snapshotter creates snapshots for all metrics."""
        await set_tenant_context(db_session, test_tenant.id)

        # Create test data: successful production deployments
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=28)
        window_end = now

        # Add commits
        commit1 = DBCommit(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            sha="a" * 40,
            message="Initial commit",
            author_name="Test Author",
            author_email="test@example.com",
            authored_at=now - timedelta(days=10),
            committed_at=now - timedelta(days=10),
        )
        commit2 = DBCommit(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            sha="b" * 40,
            message="Feature commit",
            author_name="Test Author",
            author_email="test@example.com",
            authored_at=now - timedelta(days=5),
            committed_at=now - timedelta(days=5),
        )
        db_session.add_all([commit1, commit2])
        await db_session.flush()

        # Add merged PR
        pr = DBPullRequest(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            provider="github",
            external_id="1",
            title="Feature PR",
            state="merged",
            merge_method="merge",
            merge_commit_sha="b" * 40,
            base_branch="main",
            head_branch="feature",
            opened_at=now - timedelta(days=10),
            merged_at=now - timedelta(days=4),
            closed_at=now - timedelta(days=4),
            raw_data={},
        )
        db_session.add(pr)
        await db_session.flush()

        # Link PR to commits
        from dora_platform.db.models import PRCommit
        pr_commit1 = PRCommit(pull_request_id=pr.id, commit_id=commit1.id, position=0)
        pr_commit2 = PRCommit(pull_request_id=pr.id, commit_id=commit2.id, position=1)
        db_session.add_all([pr_commit1, pr_commit2])
        await db_session.flush()

        # Add successful production deployment
        deployment = DBDeployment(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            provider="github",
            external_id="deploy-1",
            environment="production",
            sha="b" * 40,
            status="success",
            deployed_at=now - timedelta(days=3),
            finished_at=now - timedelta(days=3, hours=-1),
            raw_data={},
        )
        db_session.add(deployment)
        await db_session.flush()

        # Link deployment to commits
        from dora_platform.db.models import DeploymentCommit
        dep_commit = DeploymentCommit(deployment_id=deployment.id, commit_id=commit2.id, position=0)
        db_session.add(dep_commit)
        await db_session.flush()

        # Add failed deployment for CFR and recovery
        failed_deployment = DBDeployment(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            provider="github",
            external_id="deploy-2",
            environment="production",
            sha="c" * 40,
            status="failed",
            deployed_at=now - timedelta(days=2),
            finished_at=now - timedelta(days=2, hours=-1),
            raw_data={},
        )
        db_session.add(failed_deployment)
        await db_session.flush()

        # Add incident linked to failed deployment
        incident = DBIncident(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            provider="github",
            external_id="1",
            title="Production outage",
            state="resolved",
            severity="critical",
            source="labeled_issue",
            started_at=now - timedelta(days=2, hours=-2),
            resolved_at=now - timedelta(days=2, hours=-1),
            raw_data={"body": f"caused by {failed_deployment.sha}"},
        )
        db_session.add(incident)
        await db_session.flush()

        # Add incident-deployment link
        incident_link = DBIncidentDeploymentLink(
            tenant_id=test_tenant.id,
            incident_id=incident.id,
            deployment_id=failed_deployment.id,
            rule_id="R2",
            evidence={"rule": "R2", "matched_field": "body", "matched_value": failed_deployment.sha},
            created_by="system",
        )
        db_session.add(incident_link)
        await db_session.flush()

        # Create Snapshotter and compute snapshots
        snapshotter = Snapshotter(db_session, test_tenant.id, LinkingEngine(r3_enabled=False))
        snapshots = await snapshotter.compute_snapshots(
            scope="tenant",
            scope_id=None,
            window_types=["rolling_28d"],
        )

        # Verify snapshots were created for all metrics
        assert len(snapshots) >= 6  # deployment_frequency, deploy_days, lead_time, lead_time_commit_to_deploy, cfr, recovery, rework

        # Check each metric type exists
        metric_names = {s.metric for s in snapshots}
        expected_metrics = {
            "deployment_frequency",
            "deploy_days",
            "lead_time",
            "lead_time_commit_to_deploy",
            "change_failure_rate",
            "failed_deployment_recovery_time",
            "deployment_rework_rate",
        }
        for metric in expected_metrics:
            assert metric in metric_names, f"Missing metric: {metric}"

        # Verify snapshots have correct tenant and definition version
        for snapshot in snapshots:
            assert snapshot.tenant_id == test_tenant.id
            assert snapshot.scope == "tenant"
            assert snapshot.definition_version.startswith("ADR-")
            assert snapshot.computed_at is not None

    async def test_snapshotter_idempotent_upsert(
        self, db_session: AsyncSession, test_tenant: Tenant, test_repo: Repository
    ):
        """Test that running Snapshotter twice creates same snapshots (idempotent)."""
        await set_tenant_context(db_session, test_tenant.id)

        # Add minimal test data
        now = datetime.now(timezone.utc)
        deployment = DBDeployment(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            provider="github",
            external_id="deploy-1",
            environment="production",
            sha="a" * 40,
            status="success",
            deployed_at=now - timedelta(days=5),
            finished_at=now - timedelta(days=5, hours=-1),
            raw_data={},
        )
        db_session.add(deployment)
        await db_session.flush()

        # First run
        snapshotter = Snapshotter(db_session, test_tenant.id, LinkingEngine(r3_enabled=False))
        snapshots1 = await snapshotter.compute_snapshots(
            scope="tenant",
            scope_id=None,
            window_types=["rolling_28d"],
        )

        # Second run with same data
        snapshots2 = await snapshotter.compute_snapshots(
            scope="tenant",
            scope_id=None,
            window_types=["rolling_28d"],
        )

        # Should have same number of snapshots
        assert len(snapshots1) == len(snapshots2)

        # Each snapshot should have same values
        for s1, s2 in zip(snapshots1, snapshots2):
            assert s1.metric == s2.metric
            assert s1.value == s2.value
            assert s1.status == s2.status
            assert s1.n == s2.n
            assert s1.definition_version == s2.definition_version

    async def test_recompute_all_snapshots_convenience_function(
        self, db_session: AsyncSession, test_tenant: Tenant, test_repo: Repository
    ):
        """Test the recompute_all_snapshots convenience function."""
        await set_tenant_context(db_session, test_tenant.id)

        # Add test data
        now = datetime.now(timezone.utc)
        deployment = DBDeployment(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            provider="github",
            external_id="deploy-1",
            environment="production",
            sha="a" * 40,
            status="success",
            deployed_at=now - timedelta(days=5),
            finished_at=now - timedelta(days=5, hours=-1),
            raw_data={},
        )
        db_session.add(deployment)
        await db_session.flush()

        # Call convenience function
        snapshots = await recompute_all_snapshots(
            db_session,
            test_tenant.id,
            window_types=["rolling_28d", "rolling_90d"],
        )

        # Should have snapshots for both window types
        assert len(snapshots) >= 14  # 7 metrics * 2 window types

        window_types = {s.window_type for s in snapshots}
        assert "rolling_28d" in window_types
        assert "rolling_90d" in window_types

    async def test_snapshotter_scope_project(
        self, db_session: AsyncSession, test_tenant: Tenant, test_project: Project, test_repo: Repository
    ):
        """Test Snapshotter with project scope."""
        await set_tenant_context(db_session, test_tenant.id)

        # Add deployment for the project's repo
        now = datetime.now(timezone.utc)
        deployment = DBDeployment(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            provider="github",
            external_id="deploy-1",
            environment="production",
            sha="a" * 40,
            status="success",
            deployed_at=now - timedelta(days=5),
            finished_at=now - timedelta(days=5, hours=-1),
            raw_data={},
        )
        db_session.add(deployment)
        await db_session.flush()

        snapshotter = Snapshotter(db_session, test_tenant.id, LinkingEngine(r3_enabled=False))
        snapshots = await snapshotter.compute_snapshots(
            scope="project",
            scope_id=test_project.id,
            window_types=["rolling_28d"],
        )

        assert len(snapshots) >= 7
        for snapshot in snapshots:
            assert snapshot.scope == "project"
            assert snapshot.scope_id == test_project.id

    async def test_snapshotter_scope_repository(
        self, db_session: AsyncSession, test_tenant: Tenant, test_repo: Repository
    ):
        """Test Snapshotter with repository scope."""
        await set_tenant_context(db_session, test_tenant.id)

        # Add deployment
        now = datetime.now(timezone.utc)
        deployment = DBDeployment(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            provider="github",
            external_id="deploy-1",
            environment="production",
            sha="a" * 40,
            status="success",
            deployed_at=now - timedelta(days=5),
            finished_at=now - timedelta(days=5, hours=-1),
            raw_data={},
        )
        db_session.add(deployment)
        await db_session.flush()

        snapshotter = Snapshotter(db_session, test_tenant.id, LinkingEngine(r3_enabled=False))
        snapshots = await snapshotter.compute_snapshots(
            scope="repository",
            scope_id=test_repo.id,
            window_types=["rolling_28d"],
        )

        assert len(snapshots) >= 7
        for snapshot in snapshots:
            assert snapshot.scope == "repository"
            assert snapshot.scope_id == test_repo.id

    async def test_snapshotter_handles_no_data(
        self, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test Snapshotter returns appropriate status when no data."""
        await set_tenant_context(db_session, test_tenant.id)

        snapshotter = Snapshotter(db_session, test_tenant.id, LinkingEngine(r3_enabled=False))
        snapshots = await snapshotter.compute_snapshots(
            scope="tenant",
            scope_id=None,
            window_types=["rolling_28d"],
        )

        # Should still create snapshots with appropriate status (NO_EVENTS or UNDETECTABLE)
        assert len(snapshots) == 7  # All 7 metrics

        for snapshot in snapshots:
            assert snapshot.status in ("no_events", "undetectable")
            assert snapshot.n == 0
            assert snapshot.value is None

    async def test_metric_snapshots_unique_constraint(
        self, db_session: AsyncSession, test_tenant: Tenant, test_repo: Repository
    ):
        """Test that unique constraint prevents duplicate snapshots."""
        await set_tenant_context(db_session, test_tenant.id)

        # Use a fixed time for reproducibility
        fixed_now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        # Add deployment
        deployment = DBDeployment(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            provider="github",
            external_id="deploy-1",
            environment="production",
            sha="a" * 40,
            status="success",
            deployed_at=fixed_now - timedelta(days=5),
            finished_at=fixed_now - timedelta(days=5, hours=-1),
            raw_data={},
        )
        db_session.add(deployment)
        await db_session.flush()

        # Create a fixed window
        from dora_platform.domain.models import Window
        window = Window(
            window_type="rolling_28d",
            start=fixed_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            end=fixed_now.replace(hour=23, minute=59, second=59, microsecond=999999),
        )

        # Create a simple domain deployment object without lazy loading
        from dora_platform.domain.models import Deployment
        domain_deployment = Deployment(
            id=deployment.id,
            repository_id=deployment.repository_id,
            provider=deployment.provider,
            external_id=deployment.external_id,
            environment=deployment.environment,
            sha=deployment.sha,
            status=deployment.status,
            deployed_at=deployment.deployed_at,
            finished_at=deployment.finished_at,
            commits=[],
        )

        # Compute metrics once using domain objects
        from dora_platform.metrics import compute_deployment_frequency_with_days
        freq_result = compute_deployment_frequency_with_days(
            deployments=[domain_deployment],
            window=window,
            now=fixed_now,
            source_configured=True,
            source_healthy=True,
        )

        # Upsert the same snapshot twice
        from dora_platform.db.models import MetricSnapshot
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        snapshot_data = {
            "tenant_id": test_tenant.id,
            "scope": "tenant",
            "scope_id": None,
            "metric": "deployment_frequency",
            "window_type": window.window_type,
            "window_start": window.start,
            "window_end": window.end,
            "definition_version": freq_result["deployment_frequency"].definition_version,
            "status": freq_result["deployment_frequency"].status.value,
            "value": freq_result["deployment_frequency"].value,
            "unit": freq_result["deployment_frequency"].unit,
            "n": freq_result["deployment_frequency"].n,
            "evidence_ids": list(freq_result["deployment_frequency"].evidence_ids),
            "extra_metadata": freq_result["deployment_frequency"].extra or {},
        }

        # First upsert
        stmt = (
            pg_insert(MetricSnapshot)
            .values(snapshot_data)
            .on_conflict_do_update(
                index_elements=[
                    "tenant_id",
                    "scope",
                    "scope_id",
                    "metric",
                    "window_type",
                    "window_start",
                    "window_end",
                    "definition_version",
                ],
                set_=snapshot_data,
            )
            .returning(MetricSnapshot)
        )
        await db_session.execute(stmt)

        # Second upsert (same data)
        await db_session.execute(stmt)
        await db_session.flush()

        # Verify only one snapshot exists
        result = await db_session.execute(
            select(MetricSnapshot).where(
                MetricSnapshot.tenant_id == test_tenant.id,
                MetricSnapshot.metric == "deployment_frequency",
            )
        )
        snapshots = result.scalars().all()
        assert len(snapshots) == 1


class TestSnapshotRecomputeWithRawEvents:
    """Test full pipeline from raw events to snapshots."""

    @pytest.fixture
    async def test_tenant(self, db_session: AsyncSession) -> Tenant:
        """Create a test tenant."""
        tenant = Tenant(
            name="Raw Event Tenant",
            slug=f"raw-event-tenant-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(tenant)
        await db_session.flush()
        await db_session.refresh(tenant)
        return tenant

    @pytest.fixture
    async def test_project(self, db_session: AsyncSession, test_tenant: Tenant) -> Project:
        """Create a test project."""
        await set_tenant_context(db_session, test_tenant.id)
        project = Project(
            tenant_id=test_tenant.id,
            name="Test Project",
            slug=f"test-project-{uuid.uuid4().hex[:8]}",
            provider="github",
        )
        db_session.add(project)
        await db_session.flush()
        await db_session.refresh(project)
        return project

    @pytest.fixture
    async def test_repo(self, db_session: AsyncSession, test_tenant: Tenant, test_project: Project) -> Repository:
        """Create a test repository."""
        await set_tenant_context(db_session, test_tenant.id)
        repo = Repository(
            tenant_id=test_tenant.id,
            project_id=test_project.id,
            name=f"test-repo-{uuid.uuid4().hex[:8]}",
            provider="github",
            external_id="12345",
            url="https://github.com/test/test-repo",
        )
        db_session.add(repo)
        await db_session.flush()
        await db_session.refresh(repo)
        return repo

    async def test_raw_event_to_snapshot_pipeline(
        self, db_session: AsyncSession, test_tenant: Tenant, test_repo: Repository
    ):
        """Test full pipeline: raw events → normalized → snapshots."""
        await set_tenant_context(db_session, test_tenant.id)

        # Use a fixed time that's in the future relative to test data
        # so the rolling_28d window includes all test data
        fixed_now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        # Add commit (authored 7 days before fixed_now)
        commit = DBCommit(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            sha="d" * 40,
            message="Feature work",
            author_name="Developer",
            author_email="dev@example.com",
            authored_at=fixed_now - timedelta(days=7),
            committed_at=fixed_now - timedelta(days=7),
        )
        db_session.add(commit)
        await db_session.flush()

        # Add PR (merged 3 days before fixed_now)
        pr = DBPullRequest(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            provider="github",
            external_id="42",
            title="Add feature",
            state="merged",
            merge_method="squash",
            merge_commit_sha="e" * 40,
            base_branch="main",
            head_branch="feature/add-feature",
            opened_at=fixed_now - timedelta(days=7),
            merged_at=fixed_now - timedelta(days=3),
            closed_at=fixed_now - timedelta(days=3),
            raw_data={},
        )
        db_session.add(pr)
        await db_session.flush()

        # Link PR to commit
        from dora_platform.db.models import PRCommit
        pr_commit = PRCommit(pull_request_id=pr.id, commit_id=commit.id, position=0)
        db_session.add(pr_commit)
        await db_session.flush()

        # Add deployment (deployed 2 days before fixed_now)
        deployment = DBDeployment(
            tenant_id=test_tenant.id,
            repository_id=test_repo.id,
            provider="github",
            external_id="deploy-100",
            environment="production",
            sha="e" * 40,
            status="success",
            deployed_at=fixed_now - timedelta(days=2),
            finished_at=fixed_now - timedelta(days=2, hours=-1),
            raw_data={},
        )
        db_session.add(deployment)
        await db_session.flush()

        # Link deployment to commit
        from dora_platform.db.models import DeploymentCommit
        dep_commit = DeploymentCommit(deployment_id=deployment.id, commit_id=commit.id, position=0)
        db_session.add(dep_commit)
        await db_session.flush()

        # Compute snapshots with fixed time
        snapshotter = Snapshotter(db_session, test_tenant.id, LinkingEngine(r3_enabled=False))
        # We need to monkey-patch _generate_windows to use fixed_now
        original_generate = snapshotter._generate_windows

        def fixed_windows(window_types, _):
            return original_generate(window_types, fixed_now)

        snapshotter._generate_windows = fixed_windows

        snapshots = await snapshotter.compute_snapshots(
            scope="tenant",
            scope_id=None,
            window_types=["rolling_28d"],
        )

        # Verify we get meaningful metrics
        assert len(snapshots) == 7

        # Check deployment frequency
        df = next(s for s in snapshots if s.metric == "deployment_frequency")
        assert df.status == "ok"
        assert df.value == 1.0
        assert df.n == 1

        # Check lead time
        lt = next(s for s in snapshots if s.metric == "lead_time")
        assert lt.status == "ok"
        assert lt.value is not None
        assert lt.value > 0
        assert lt.n == 1
        assert "p75" in lt.extra_metadata
        assert "p90" in lt.extra_metadata

        # Check deploy days
        dd = next(s for s in snapshots if s.metric == "deploy_days")
        assert dd.status == "ok"
        assert dd.value == 1.0
        assert dd.n == 1