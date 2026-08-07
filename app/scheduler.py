from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import load_config
from app.jobs import poll_and_run_jobs


LOGGER = logging.getLogger(__name__)


def start_job_scheduler() -> Any | None:
    config = load_config()
    if not config.job_runner_enabled:
        LOGGER.info("Job runner is disabled")
        return None

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        LOGGER.error("APScheduler is not installed; job runner cannot start")
        return None

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        poll_and_run_jobs,
        "interval",
        seconds=config.job_request_interval_seconds,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
        id="request-and-run-jobs",
        replace_existing=True,
    )
    scheduler.start()
    LOGGER.info(
        "Job runner started with %s second interval",
        config.job_request_interval_seconds,
    )

    return scheduler


def stop_job_scheduler(scheduler: Any | None) -> None:
    if scheduler is None:
        return

    scheduler.shutdown(wait=False)
    LOGGER.info("Job runner stopped")
