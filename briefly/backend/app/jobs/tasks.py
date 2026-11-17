"""Unit-of-work wrappers the scheduler and the CLI both call."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.db import session_scope
from app.enums import ProcessingStatus
from app.models import PipelineRun
from app.pipeline import orchestrator
from app.podcast import service as podcast_service

log = logging.getLogger("briefly.jobs")


def _record(kind: str, fn) -> dict:
    with session_scope() as db:
        run = PipelineRun(kind=kind, status=ProcessingStatus.PROCESSING)
        db.add(run)
        db.flush()
        try:
            stats = fn(db)
            run.status = ProcessingStatus.READY
            run.stats = stats or {}
        except Exception as exc:
            run.status = ProcessingStatus.FAILED
            run.error = f"{type(exc).__name__}: {exc}"
            run.finished_at = datetime.now(UTC)
            log.exception("job %s failed", kind)
            raise
        run.finished_at = datetime.now(UTC)
        return run.stats


def job_refresh_news() -> dict:
    """Ingest, cluster, extract, summarise, rank, gate."""
    return _record("refresh_news", lambda db: orchestrator.run_full(db))


def job_process_only() -> dict:
    return _record("process", lambda db: orchestrator.run_processing(db))


def job_daily_podcast() -> dict:
    """Collect -> rank -> narrate -> quality-check -> voice -> store -> publish."""

    def _run(db) -> dict:
        episode = podcast_service.generate_daily_episode(db)
        if episode is None:
            return {"created": False, "reason": "no published stories"}
        if episode.status == ProcessingStatus.FLAGGED:
            return {
                "created": True,
                "voiced": False,
                "status": episode.status,
                "reason": "failed quality control; flagged for review",
                "qc": episode.qc_report,
            }
        podcast_service.synthesise_episode(db, episode)
        return {
            "created": True,
            "voiced": True,
            "status": episode.status,
            "slug": episode.slug,
            "duration_seconds": episode.audio_duration_seconds,
            "stories": len(episode.entries),
        }

    return _record("daily_podcast", _run)


def job_deep_dive() -> dict:
    def _run(db) -> dict:
        episode = podcast_service.generate_deep_dive_episode(db)
        if episode is None:
            return {"created": False, "reason": "no suitable story"}
        if episode.status == ProcessingStatus.FLAGGED:
            return {"created": True, "voiced": False, "qc": episode.qc_report}
        podcast_service.synthesise_episode(db, episode)
        return {"created": True, "voiced": True, "slug": episode.slug}

    return _record("deep_dive", _run)
