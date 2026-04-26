"""
OCR Repository — All Frappe database operations for OCR Job and OCR Page.

Isolates persistence from business logic (Repository Pattern).
"""

import logging
from typing import Optional

import frappe
from frappe.utils import now_datetime

from .constants import (
    STATUS_PENDING, STATUS_RENDERING, STATUS_COMPLETED, STATUS_FAILED,
    STATUS_PROCESSING, JOB_QUEUED, JOB_RUNNING, JOB_COMPLETED, JOB_FAILED,
    JOB_PAUSED,
)
from .models import OcrJobStatus

logger = logging.getLogger(__name__)


class OcrRepository:
    """Encapsulates all Frappe DB reads/writes for OCR Job and OCR Page."""

    # ─── Job CRUD ─────────────────────────────────────────────────

    def create_job(
        self,
        zip_path: str,
        output_path: str,
        model_name: str,
        total_pages: int,
    ) -> str:
        """Insert a new OCR Job record. Returns the job name."""
        job = frappe.get_doc({
            "doctype": "OCR Job",
            "zip_path": zip_path,
            "output_path": output_path,
            "model_name": model_name,
            "status": JOB_QUEUED,
            "total_pages": total_pages,
            "completed_pages": 0,
            "failed_pages": 0,
        })
        job.insert(ignore_permissions=True)
        frappe.db.commit()
        logger.info("Created OCR Job %s — %d pages", job.name, total_pages)
        return job.name

    def create_pages(self, job_name: str, pages_data: list[dict]) -> None:
        """Insert OCR Page records with predefined data."""
        for data in pages_data:
            frappe.get_doc({
                "doctype": "OCR Page",
                "ocr_job": job_name,
                "page_number": data["page_number"],
                "source_filename": data.get("source_filename"),
                "image_path": data["image_path"],
                "status": STATUS_PENDING,
            }).insert(ignore_permissions=True)
        frappe.db.commit()
        logger.info("Created %d OCR Page records for job %s", len(pages_data), job_name)

    def get_job(self, job_name: str):
        """Fetch a live OCR Job document."""
        return frappe.get_doc("OCR Job", job_name)

    def list_jobs(self) -> list[dict]:
        """List all OCR jobs, newest first."""
        return frappe.get_all(
            "OCR Job",
            fields=[
                "name", "zip_path", "model_name", "status",
                "total_pages", "completed_pages", "failed_pages",
                "started_at", "completed_at",
            ],
            order_by="creation desc",
        )

    def delete_job(self, job_name: str) -> None:
        """Delete job and all associated page records from DB."""
        frappe.db.delete("OCR Page", {"ocr_job": job_name})
        frappe.delete_doc("OCR Job", job_name, ignore_permissions=True, ignore_missing=True)
        frappe.db.commit()
        logger.info("Deleted OCR Job records for: %s", job_name)

    # ─── Job State Transitions ────────────────────────────────────

    def mark_job_running(self, job_name: str) -> None:
        """Transition job to Running state."""
        job = self.get_job(job_name)
        job.status = JOB_RUNNING
        job.started_at = job.started_at or now_datetime()
        job.save(ignore_permissions=True)
        frappe.db.commit()

    def mark_job_paused(self, job_name: str) -> None:
        """Transition job to Paused state."""
        job = self.get_job(job_name)
        job.status = JOB_PAUSED
        job.save(ignore_permissions=True)
        frappe.db.commit()

    def finalize_job(self, job_name: str) -> str:
        """Set the final status based on remaining/failed pages. Returns final status."""
        job = self.get_job(job_name)
        remaining = self.count_pages_by_status(
            job_name, [STATUS_PENDING, STATUS_PROCESSING]
        )
        if remaining == 0:
            job.status = JOB_COMPLETED if job.failed_pages == 0 else JOB_FAILED
            job.completed_at = now_datetime()
        else:
            job.status = JOB_PAUSED
        job.save(ignore_permissions=True)
        frappe.db.commit()
        return job.status

    def update_job_counters(self, job_name: str) -> None:
        """Recalculate completed_pages and failed_pages from actual page records."""
        job = self.get_job(job_name)
        job.completed_pages = self.count_pages_by_status(job_name, [STATUS_COMPLETED])
        job.failed_pages = self.count_pages_by_status(job_name, [STATUS_FAILED])
        job.save(ignore_permissions=True)
        frappe.db.commit()

    def is_job_active(self, job_name: str) -> bool:
        """Check if the job is still in a runnable state."""
        job = self.get_job(job_name)
        return job.status in (JOB_RUNNING, JOB_QUEUED)

    def reset_job(self, job_name: str) -> None:
        """Reset all OCR progress while preserving images."""
        frappe.db.sql("""
            UPDATE `tabOCR Page`
            SET status = 'Pending', markdown_output = NULL, error = NULL, processing_time = 0
            WHERE ocr_job = %s
        """, job_name)
        job = self.get_job(job_name)
        job.status = JOB_QUEUED
        job.completed_pages = 0
        job.failed_pages = 0
        job.save(ignore_permissions=True)
        frappe.db.commit()
        logger.info("Reset OCR Job: %s", job_name)

    # ─── Page Operations ──────────────────────────────────────────

    def get_pending_pages(self, job_name: str) -> list[dict]:
        """Fetch all pages that still need processing."""
        return frappe.get_all(
            "OCR Page",
            filters={
                "ocr_job": job_name,
                "status": ["in", [STATUS_PENDING, STATUS_FAILED, STATUS_PROCESSING]],
            },
            fields=["name", "page_number", "source_filename"],
            order_by="page_number asc",
        )

    def get_all_pages(self, job_name: str) -> list[dict]:
        """Fetch all pages for a job with their status info."""
        return frappe.get_all(
            "OCR Page",
            filters={"ocr_job": job_name},
            fields=["page_number", "source_filename", "status", "processing_time", "error"],
            order_by="page_number asc",
        )

    def get_page(self, page_name: str):
        """Fetch a single OCR Page document."""
        return frappe.get_doc("OCR Page", page_name)

    def bulk_set_status(self, page_names: list[str], status: str) -> None:
        """Set status for multiple pages at once via raw SQL."""
        if not page_names:
            return
        frappe.db.sql(
            "UPDATE `tabOCR Page` SET status = %s WHERE name IN %s",
            (status, tuple(page_names)),
        )
        frappe.db.commit()

    def set_page_rendering_done(
        self, job_name: str, page_number: int, image_path: str
    ) -> None:
        """Mark a page as rendered with its image path, back to Pending for LLM."""
        frappe.db.set_value(
            "OCR Page",
            {"ocr_job": str(job_name), "page_number": page_number},
            {"image_path": image_path, "status": STATUS_PENDING},
            update_modified=False,
        )

    def save_page_result(
        self,
        page_name: str,
        markdown: str,
        processing_time: float,
    ) -> None:
        """Save a successful LLM result to a page."""
        page = self.get_page(page_name)
        page.markdown_output = markdown
        page.processing_time = round(processing_time, 2)
        page.status = STATUS_COMPLETED
        page.save(ignore_permissions=True)

    def save_page_error(self, page_name: str, error: str) -> None:
        """Save a failure to a page."""
        page = self.get_page(page_name)
        page.status = STATUS_FAILED
        page.error = error[:2000]
        page.save(ignore_permissions=True)

    def count_rendered_pages(self, job_name: str) -> int:
        """Count pages that have an image_path."""
        return frappe.db.count(
            "OCR Page",
            {"ocr_job": job_name, "image_path": ["not in", [None, ""]]},
        )

    def count_pages_by_status(self, job_name: str, statuses: list[str]) -> int:
        """Count pages matching any of the given statuses."""
        return frappe.db.count(
            "OCR Page",
            {"ocr_job": job_name, "status": ["in", statuses]},
        )

    def get_completed_page_markdowns(self, job_name: str) -> list[dict]:
        """Fetch completed pages' markdown content in order."""
        return frappe.get_all(
            "OCR Page",
            filters={"ocr_job": job_name, "status": STATUS_COMPLETED},
            fields=["page_number", "source_filename", "markdown_output"],
            order_by="page_number asc",
        )

    # ─── Status Snapshot ──────────────────────────────────────────

    def get_job_status(self, job_name: str) -> OcrJobStatus:
        """Build a full status snapshot for the API response."""
        job = self.get_job(job_name)
        pages = self.get_all_pages(job_name)
        rendered = self.count_rendered_pages(job_name)
        return OcrJobStatus(
            name=job.name,
            zip_path=job.zip_path,
            output_path=job.output_path,
            model_name=job.model_name,
            status=job.status,
            total_pages=job.total_pages,
            completed_pages=job.completed_pages,
            failed_pages=job.failed_pages,
            rendered_pages=rendered,
            started_at=str(job.started_at) if job.started_at else None,
            completed_at=str(job.completed_at) if job.completed_at else None,
            pages=pages,
        )
