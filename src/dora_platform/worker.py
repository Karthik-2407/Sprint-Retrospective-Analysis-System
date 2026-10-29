"""APScheduler worker for background jobs.

Real implementations for Phase 1: reconcile_recent, backfill_historical, recompute_snapshots.
"""

import signal
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from dora_platform.config import settings
from dora_platform.ingestion import (
    reconcile_recent,
    backfill_historical,
    create_backfill_run,
    process_raw_events_batch,
    retry_quarantined,
)
from dora_platform.ingestion.snapshotter import Snapshotter
from dora_platform.observability.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def reconcile_recent() -> None:
    """
    Reconcile recent events from providers.

    Runs every RECONCILE_INTERVAL_MINUTES (default: 15 min).
    """
    logger.info("reconcile_recent_started")
    try:
        stats = await reconcile_recent(hours=24, batch_size=100)
        logger.info("reconcile_recent_completed", **stats)
    except Exception as e:
        logger.error("reconcile_recent_failed", error=str(e))
        raise


async def backfill_historical() -> None:
    """
    Backfill historical data.

    Runs daily at 02:00. Creates ingestion runs for each active provider connection.
    """
    logger.info("backfill_historical_started")
    try:
        from dora_platform.db.engine import async_session_maker
        from dora_platform.db.models import ProviderConnection
        from sqlalchemy import select

        async with async_session_maker() as session:
            stmt = select(ProviderConnection).where(ProviderConnection.is_active.is_(True))
            result = await session.execute(stmt)
            connections = result.scalars().all()

            for conn in connections:
                run_id = await create_backfill_run(
                    tenant_id=conn.tenant_id,
                    provider_connection_id=str(conn.id),
                    since=None,  # Full history
                )
                logger.info("backfill_run_created", run_id=run_id, connection_id=str(conn.id))
                # Execute the backfill
                await backfill_historical(run_id)

        logger.info("backfill_historical_completed", connections_processed=len(connections))
    except Exception as e:
        logger.error("backfill_historical_failed", error=str(e))
        raise


async def recompute_snapshots() -> None:
    """
    Recompute metric snapshots with latest definitions.

    Runs every 6 hours.
    """
    logger.info("recompute_snapshots_started")
    try:
        from dora_platform.db.engine import async_session_maker
        from dora_platform.db.models import Project
        from dora_platform.db.tenant import set_tenant_context
        from sqlalchemy import select

        async with async_session_maker() as session:
            # Get all projects
            stmt = select(Project)
            result = await session.execute(stmt)
            projects = result.scalars().all()

            snapshotter = Snapshotter()
            total_snapshots = 0

            for project in projects:
                # Set tenant context for RLS
                set_tenant_context(project.tenant_id)
                try:
                    count = await snapshotter.compute_snapshots(
                        session, project.tenant_id, project_id=str(project.id)
                    )
                    total_snapshots += count
                    logger.info("snapshots_computed", project_id=str(project.id), count=count)
                finally:
                    set_tenant_context(None)

            logger.info("recompute_snapshots_completed", total_snapshots=total_snapshots)
    except Exception as e:
        logger.error("recompute_snapshots_failed", error=str(e))
        raise


async def process_ingestion_queue() -> None:
    """
    Process pending raw events through normalizers.

    Runs every minute.
    """
    logger.debug("process_ingestion_queue_started")
    try:
        processed = await process_raw_events_batch(batch_size=100)
        if processed > 0:
            logger.info("process_ingestion_queue_completed", processed=processed)
    except Exception as e:
        logger.error("process_ingestion_queue_failed", error=str(e))
        raise


async def process_quarantine() -> None:
    """
    Retry quarantined events.

    Runs every hour.
    """
    logger.debug("process_quarantine_started")
    try:
        stats = await retry_quarantined(max_events=50)
        if stats["retried"] > 0:
            logger.info("process_quarantine_completed", **stats)
    except Exception as e:
        logger.error("process_quarantine_failed", error=str(e))
        raise


def setup_jobs() -> None:
    """Configure and add scheduled jobs."""
    # Process ingestion queue - every minute
    scheduler.add_job(
        process_ingestion_queue,
        IntervalTrigger(minutes=1),
        id="process_ingestion_queue",
        name="Process raw events queue",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    # Reconcile recent - every N minutes
    scheduler.add_job(
        reconcile_recent,
        IntervalTrigger(minutes=settings.reconcile_interval_minutes),
        id="reconcile_recent",
        name="Reconcile recent provider events",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    # Backfill historical - daily at 02:00
    scheduler.add_job(
        backfill_historical,
        CronTrigger(hour=2, minute=0),
        id="backfill_historical",
        name="Backfill historical data",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    # Recompute snapshots - every 6 hours
    scheduler.add_job(
        recompute_snapshots,
        IntervalTrigger(hours=6),
        id="recompute_snapshots",
        name="Recompute metric snapshots",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    # Process quarantine - every hour
    scheduler.add_job(
        process_quarantine,
        IntervalTrigger(hours=1),
        id="process_quarantine",
        name="Retry quarantined events",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    logger.info("jobs_scheduled", job_count=len(scheduler.get_jobs()))


def setup_signal_handlers() -> None:
    """Set up graceful shutdown handlers."""

    def shutdown_handler(signum: int, frame: object) -> None:
        logger.info("shutdown_signal_received", signal=signum)
        scheduler.shutdown(wait=True)
        logger.info("scheduler_shutdown_complete")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)


@asynccontextmanager
async def lifespan() -> AsyncGenerator[None]:
    """Worker lifespan context manager."""
    logger.info("worker_starting", version=settings.app_version)
    setup_jobs()
    setup_signal_handlers()
    scheduler.start()
    logger.info("worker_started")
    try:
        yield
    finally:
        logger.info("worker_stopping")
        scheduler.shutdown(wait=True)
        logger.info("worker_stopped")


async def main() -> None:
    """Main entry point for the worker."""
    async with lifespan():
        # Keep the worker running
        import asyncio

        while True:
            await asyncio.sleep(60)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())