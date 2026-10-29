#!/usr/bin/env python
"""Idempotent demo data loader for DORA Platform.

Loads a demo tenant with sample projects and repositories.
Run with: python scripts/seed.py
"""

import asyncio
import sys
import uuid

# On Windows, psycopg async requires SelectorEventLoop instead of ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dora_platform.db import create_engine, get_session_factory
from dora_platform.db.models import Project, Repository, Tenant


async def seed_demo_data(session: AsyncSession) -> None:
    """Seed demo data idempotently."""

    # Check if demo tenant already exists
    result = await session.execute(select(Tenant).where(Tenant.slug == "demo"))
    tenant = result.scalar_one_or_none()

    if tenant is None:
        tenant = Tenant(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            name="Demo Tenant",
            slug="demo",
            settings={
                "description": "Demo tenant for DORA Platform",
                "created_by": "seed_script",
            },
        )
        session.add(tenant)
        await session.flush()
    else:
        pass

    # Check if demo project exists
    result = await session.execute(
        select(Project).where(Project.slug == "demo-project", Project.tenant_id == tenant.id)
    )
    project = result.scalar_one_or_none()

    if project is None:
        project = Project(
            id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            tenant_id=tenant.id,
            name="Demo Project",
            slug="demo-project",
            provider="github",
            provider_config={
                "org": "demo-org",
                "repo": "demo-repo",
            },
        )
        session.add(project)
        await session.flush()
    else:
        pass

    # Check if demo repository exists
    result = await session.execute(
        select(Repository).where(
            Repository.project_id == project.id, Repository.external_id == "123456789"
        )
    )
    repo = result.scalar_one_or_none()

    if repo is None:
        repo = Repository(
            id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
            project_id=project.id,
            name="demo-repo",
            provider="github",
            external_id="123456789",
            url="https://github.com/demo-org/demo-repo",
            default_branch="main",
        )
        session.add(repo)
    else:
        pass

    # Add a second project for course/cohort demo
    result = await session.execute(
        select(Project).where(Project.slug == "course-101", Project.tenant_id == tenant.id)
    )
    course_project = result.scalar_one_or_none()

    if course_project is None:
        course_project = Project(
            id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
            tenant_id=tenant.id,
            name="Course 101 - Software Engineering",
            slug="course-101",
            provider="github",
            provider_config={
                "org": "university-cs",
                "classroom": "course-101-fall-2026",
            },
        )
        session.add(course_project)
        await session.flush()

        # Add team repositories
        for team_num in range(1, 4):
            team_slug = f"team-{team_num}"
            result = await session.execute(
                select(Repository).where(
                    Repository.project_id == course_project.id, Repository.name == team_slug
                )
            )
            team_repo = result.scalar_one_or_none()

            if team_repo is None:
                team_repo = Repository(
                    id=uuid.UUID(f"00000000-0000-0000-0000-00000000000{4 + team_num}"),
                    project_id=course_project.id,
                    name=team_slug,
                    provider="github",
                    external_id=f"98765432{team_num}",
                    url=f"https://github.com/university-cs/course-101-fall-2026-{team_slug}",
                    default_branch="main",
                )
                session.add(team_repo)

    await session.commit()


async def main() -> None:
    """Main entry point."""

    # Override DATABASE_URL for local development (replace 'db' with 'localhost:5433')
    import os

    from dora_platform.config import get_settings
    from dora_platform.db.engine import reset_engine

    # Clear settings cache to pick up new DATABASE_URL
    get_settings.cache_clear()

    settings = get_settings()
    db_url = str(settings.database_url)
    if "@db:" in db_url:
        # Replace 'db:5432' with 'localhost:5433' (Docker host port mapping)
        db_url = db_url.replace("@db:5432", "@localhost:5433")
        os.environ["DATABASE_URL"] = db_url
        # Clear cache again after modifying env var
        get_settings.cache_clear()
        # Reset engine to pick up new URL
        reset_engine()

    # Create engine and session
    engine = create_engine()
    async with get_session_factory()() as session:
        try:
            await seed_demo_data(session)
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
