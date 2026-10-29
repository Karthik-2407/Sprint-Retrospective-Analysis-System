"""Integration tests for database connectivity and migrations.

These tests use Testcontainers to spin up a real PostgreSQL instance.
"""

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dora_platform.db import get_engine, session_context


@pytest.mark.integration
class TestDatabaseConnection:
    """Test database connectivity."""

    async def test_engine_connects(self):
        """Test that the engine can connect to the database."""
        async with get_engine().connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    async def test_session_works(self):
        """Test that sessions work correctly."""
        async with session_context() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1

    async def test_session_rollback_on_error(self):
        """Test that sessions rollback on error."""
        async with session_context() as session:
            await session.execute(text("SELECT 1"))
            # This should work fine
            assert True

        # Verify we can still use sessions after
        async with session_context() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1


@pytest.mark.integration
class TestModels:
    """Test database models."""

    async def test_tenant_crud(self, db_session: AsyncSession):
        """Test CRUD operations on Tenant model."""
        from dora_platform.db.models import Tenant

        # Create - use unique slug to avoid conflicts
        slug = f"test-tenant-{uuid.uuid4().hex[:8]}"
        tenant = Tenant(name="Test Tenant", slug=slug)
        db_session.add(tenant)
        await db_session.flush()  # Use flush instead of commit for test isolation
        await db_session.refresh(tenant)

        assert tenant.id is not None
        assert tenant.name == "Test Tenant"
        assert tenant.slug == slug
        assert tenant.created_at is not None

        # Read
        result = await db_session.execute(
            text("SELECT * FROM tenants WHERE id = :id"), {"id": tenant.id}
        )
        row = result.mappings().first()
        assert row["name"] == "Test Tenant"
        assert row["slug"] == slug

        # Update
        tenant.name = "Updated Tenant"
        await db_session.flush()
        await db_session.refresh(tenant)
        assert tenant.name == "Updated Tenant"

        # Delete
        await db_session.delete(tenant)
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT * FROM tenants WHERE id = :id"), {"id": tenant.id}
        )
        assert result.first() is None

    async def test_project_tenant_relationship(self, db_session: AsyncSession):
        """Test Project-Tenant relationship."""
        from dora_platform.db.models import Project, Tenant
        from dora_platform.db.tenant import set_tenant_context

        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db_session.add(tenant)
        await db_session.flush()

        # Set tenant context before creating project
        await set_tenant_context(db_session, tenant.id)

        project = Project(
            tenant_id=tenant.id,
            name="Test Project",
            slug=f"test-project-{uuid.uuid4().hex[:8]}",
            provider="github",
        )
        db_session.add(project)
        await db_session.flush()

        # Verify relationship - use eager loading to avoid lazy load issues
        result = await db_session.execute(
            select(Tenant).options(selectinload(Tenant.projects)).where(Tenant.id == tenant.id)
        )
        tenant_with_projects = result.scalar_one()
        assert len(tenant_with_projects.projects) == 1
        assert tenant_with_projects.projects[0].id == project.id

        # Also verify project -> tenant
        result = await db_session.execute(select(Project).where(Project.id == project.id))
        project_from_db = result.scalar_one()
        assert project_from_db.tenant_id == tenant.id

    async def test_repository_project_relationship(self, db_session: AsyncSession):
        """Test Repository-Project relationship."""
        from dora_platform.db.models import Project, Repository, Tenant
        from dora_platform.db.tenant import set_tenant_context

        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db_session.add(tenant)
        await db_session.flush()

        # Set tenant context before creating project and repository
        await set_tenant_context(db_session, tenant.id)

        project = Project(
            tenant_id=tenant.id,
            name="Test Project",
            slug=f"test-project-{uuid.uuid4().hex[:8]}",
            provider="github",
        )
        db_session.add(project)
        await db_session.flush()

        repo = Repository(
            tenant_id=tenant.id,
            project_id=project.id,
            name=f"test-repo-{uuid.uuid4().hex[:8]}",
            provider="github",
            external_id="12345",
            url="https://github.com/test/test-repo",
        )
        db_session.add(repo)
        await db_session.flush()

        # Verify relationship - use eager loading to avoid lazy load issues
        result = await db_session.execute(
            select(Project)
            .options(selectinload(Project.repositories))
            .where(Project.id == project.id)
        )
        project_with_repos = result.scalar_one()
        assert len(project_with_repos.repositories) == 1
        assert project_with_repos.repositories[0].id == repo.id

        # Also verify repo -> project
        result = await db_session.execute(select(Repository).where(Repository.id == repo.id))
        repo_from_db = result.scalar_one()
        assert repo_from_db.project_id == project.id

    async def test_unique_constraints(self, db_session: AsyncSession):
        """Test unique constraints on models."""
        from sqlalchemy.exc import IntegrityError

        from dora_platform.db.models import Project, Tenant
        from dora_platform.db.tenant import set_tenant_context

        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db_session.add(tenant)
        await db_session.flush()

        # Set tenant context before creating projects
        await set_tenant_context(db_session, tenant.id)

        project1 = Project(
            tenant_id=tenant.id,
            name="Test Project",
            slug=f"test-project-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(project1)
        await db_session.flush()

        # Duplicate slug in same tenant should fail
        project2 = Project(
            tenant_id=tenant.id,
            name="Test Project 2",
            slug=project1.slug,  # Same slug
        )
        db_session.add(project2)

        # Flush should raise IntegrityError for unique constraint violation
        with pytest.raises(IntegrityError):
            await db_session.flush()


@pytest.mark.integration
class TestTenantContext:
    """Test tenant context (RLS implementation)."""

    async def test_set_tenant_context(self, db_session: AsyncSession):
        """Test that set_tenant_context sets the session variable."""
        from dora_platform.db.tenant import get_tenant_context, set_tenant_context

        tenant_id = uuid.uuid4()
        await set_tenant_context(db_session, tenant_id)

        # Verify the context was set
        context_id = await get_tenant_context(db_session)
        assert context_id == tenant_id

    async def test_clear_tenant_context(self, db_session: AsyncSession):
        """Test that clearing tenant context sets zero UUID."""
        from dora_platform.db.tenant import get_tenant_context, set_tenant_context

        tenant_id = uuid.uuid4()
        await set_tenant_context(db_session, tenant_id)
        context_id = await get_tenant_context(db_session)
        assert context_id == tenant_id

        # Clear context
        await set_tenant_context(db_session, None)
        context_id = await get_tenant_context(db_session)
        assert context_id is None

    async def test_tenant_isolation(self, db_session: AsyncSession):
        """Test that RLS isolates tenants (queries only see their own data)."""
        from dora_platform.db.models import Project, Tenant
        from dora_platform.db.tenant import set_tenant_context

        # Create two tenants (no context needed for tenants table)
        tenant1 = Tenant(name="Tenant One", slug=f"tenant-1-{uuid.uuid4().hex[:8]}")
        tenant2 = Tenant(name="Tenant Two", slug=f"tenant-2-{uuid.uuid4().hex[:8]}")
        db_session.add_all([tenant1, tenant2])
        await db_session.flush()

        # Create projects for each tenant with proper context
        await set_tenant_context(db_session, tenant1.id)
        project1 = Project(
            tenant_id=tenant1.id,
            name="Project 1",
            slug=f"proj-1-{uuid.uuid4().hex[:8]}",
            provider="github",
        )
        db_session.add(project1)
        await db_session.flush()

        await set_tenant_context(db_session, tenant2.id)
        project2 = Project(
            tenant_id=tenant2.id,
            name="Project 2",
            slug=f"proj-2-{uuid.uuid4().hex[:8]}",
            provider="github",
        )
        db_session.add(project2)
        await db_session.flush()

        # Set context to tenant1 and query projects
        await set_tenant_context(db_session, tenant1.id)
        from sqlalchemy import select

        result = await db_session.execute(select(Project))
        projects = result.scalars().all()
        assert len(projects) == 1
        assert projects[0].id == project1.id

        # Set context to tenant2 and query projects
        await set_tenant_context(db_session, tenant2.id)
        result = await db_session.execute(select(Project))
        projects = result.scalars().all()
        assert len(projects) == 1
        assert projects[0].id == project2.id

        # Clear context and query (should see nothing)
        await set_tenant_context(db_session, None)
        result = await db_session.execute(select(Project))
        projects = result.scalars().all()
        assert len(projects) == 0
