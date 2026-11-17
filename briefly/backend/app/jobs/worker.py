"""Standalone scheduler process.

Runs the automated pipeline without serving HTTP, so the API can be scaled
horizontally while exactly one worker owns the jobs. Running the scheduler
inside several API replicas would produce duplicate episodes.

    python -m app.jobs.worker
"""

from __future__ import annotations

import logging
import signal
import sys
import threading

from app.config import get_settings
from app.jobs.scheduler import shutdown_scheduler, start_scheduler

log = logging.getLogger("briefly.worker")


def main() -> int:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    if not settings.scheduler_enabled:
        log.error(
            "BRIEFLY_SCHEDULER_ENABLED is false, so this worker has nothing to do. "
            "Set it to true, or run stages by hand with scripts/run_pipeline.py."
        )
        return 1

    scheduler = start_scheduler()
    if scheduler is None:
        return 1

    stop = threading.Event()

    def handle(signum, _frame):
        log.info("received signal %s; shutting down", signum)
        stop.set()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)

    log.info("worker running; jobs: %s", [job.id for job in scheduler.get_jobs()])
    stop.wait()
    shutdown_scheduler()
    log.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
