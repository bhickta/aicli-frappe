"""
OCR Tasks — Frappe background job entry points.

These are the only functions that should be enqueued via frappe.enqueue().
They create a service instance and delegate to it.
"""

import logging
from .job_service import OcrJobService

logger = logging.getLogger(__name__)


def run_ocr_job(ocr_job_name: str, max_workers: int = 3) -> None:
    """Background task: run an OCR job. Called via frappe.enqueue()."""
    logger.info("Background worker starting OCR job %s (workers=%d)", ocr_job_name, max_workers)
    OcrJobService().run_job(ocr_job_name, max_workers=max_workers)
