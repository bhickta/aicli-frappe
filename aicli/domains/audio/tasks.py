"""
Audio Tasks — Frappe background job entry points.

These are the only functions that should be enqueued via frappe.enqueue().
They create a service instance and delegate to it.
"""

import logging
from .job_service import AudioJobService

logger = logging.getLogger(__name__)


def run_audio_job(job_name: str, max_workers: int = 2) -> None:
    """Background task: run the full audio pipeline. Called via frappe.enqueue()."""
    logger.info("Background worker starting audio job %s (workers=%d)", job_name, max_workers)
    AudioJobService().run_job(job_name, max_workers=max_workers)
