"""
OCR API Endpoints — Frappe whitelisted methods for the OCR feature.

Thin controllers: validate input, delegate to OcrJobService, return response.
"""

import os
import frappe

from aicli.domains.ocr.job_service import OcrJobService
from aicli.domains.ocr.file_manager import FileManager
from aicli.domains.ocr.constants import (
    DEFAULT_DPI, DEFAULT_MAX_WORKERS, DEFAULT_MODEL,
    ENQUEUE_TIMEOUT, ENQUEUE_QUEUE,
)


def _get_service() -> OcrJobService:
    """Factory helper — single instance per request."""
    return OcrJobService()


def _get_default_model() -> str:
    """Get the default model from settings or fallback."""
    doc = frappe.get_single("AICLI Settings")
    return doc.model_name or DEFAULT_MODEL


# ─── Endpoints ────────────────────────────────────────────────────

@frappe.whitelist()
def start_ocr(pdf_path: str, model_name: str = None, dpi: int = DEFAULT_DPI, max_workers: int = DEFAULT_MAX_WORKERS):
    """Create and enqueue an OCR job."""
    svc = _get_service()
    model = model_name or _get_default_model()
    job_name = svc.create_job(pdf_path, model, int(dpi))

    frappe.enqueue(
        "aicli.domains.ocr.tasks.run_ocr_job",
        ocr_job_name=job_name,
        max_workers=int(max_workers),
        queue=ENQUEUE_QUEUE,
        timeout=ENQUEUE_TIMEOUT,
        is_async=True,
    )
    return {"job_name": job_name, "status": "Queued"}


@frappe.whitelist()
def ocr_status(job_name: str):
    """Get the current status of an OCR job."""
    return _get_service().get_status(job_name)


@frappe.whitelist()
def ocr_output(job_name: str):
    """Get the assembled markdown output."""
    return {"markdown": _get_service().get_output(job_name)}


@frappe.whitelist()
def ocr_jobs():
    """List all OCR jobs."""
    return _get_service().list_jobs()


@frappe.whitelist()
def resume_ocr(job_name: str, max_workers: int = DEFAULT_MAX_WORKERS):
    """Resume a paused or failed OCR job."""
    frappe.enqueue(
        "aicli.domains.ocr.tasks.run_ocr_job",
        ocr_job_name=job_name,
        max_workers=int(max_workers),
        queue=ENQUEUE_QUEUE,
        timeout=ENQUEUE_TIMEOUT,
        is_async=True,
    )
    return {"job_name": job_name, "status": "Resuming"}


@frappe.whitelist()
def stop_ocr(job_name: str):
    """Stop a running OCR job."""
    _get_service().stop_job(job_name)
    return {"status": "Paused"}


@frappe.whitelist()
def delete_ocr_job(job_name: str):
    """Delete an OCR job and all its data."""
    _get_service().delete_job(job_name)
    return {"ok": True}


@frappe.whitelist()
def reset_ocr_job(job_name: str):
    """Reset an OCR job — wipe progress, keep images."""
    _get_service().reset_job(job_name)
    return {"ok": True}


@frappe.whitelist()
def upload_pdf_for_ocr():
    """Upload a PDF and immediately start OCR."""
    if "file" not in frappe.request.files:
        frappe.throw("No file uploaded")

    f = frappe.request.files["file"]
    upload_dir = FileManager.get_uploads_dir()
    file_path = os.path.join(upload_dir, f.filename)
    f.save(file_path)

    model_name = frappe.request.form.get("model_name") or _get_default_model()
    dpi = int(frappe.request.form.get("dpi", DEFAULT_DPI))
    max_workers = int(frappe.request.form.get("max_workers", DEFAULT_MAX_WORKERS))

    svc = _get_service()
    job_name = svc.create_job(file_path, model_name, dpi)

    frappe.enqueue(
        "aicli.domains.ocr.tasks.run_ocr_job",
        ocr_job_name=job_name,
        max_workers=max_workers,
        queue=ENQUEUE_QUEUE,
        timeout=ENQUEUE_TIMEOUT,
        is_async=True,
    )
    return {"job_name": job_name, "pdf_path": file_path, "status": "Queued"}
