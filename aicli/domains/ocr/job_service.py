"""
OCR Job Service — Thin orchestrator that ties all domain components together.

This is the only class that composes the other components.
Each method is a high-level use case with clear logging and error handling.
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import frappe

from .constants import STATUS_PROCESSING
from .repository import OcrRepository
from .llm_caller import LlmCaller
from .markdown_writer import MarkdownWriter
from .model_manager import ModelManager
from .provider_factory import ProviderFactory
from .file_manager import FileManager

logger = logging.getLogger(__name__)


class OcrJobService:
    """Orchestrates the OCR pipeline: create, run, resume, query, delete jobs.

    Composes:
      - OcrRepository  (persistence)
      - LlmCaller       (image → markdown)
      - MarkdownWriter  (file I/O)
      - ModelManager     (LM Studio lifecycle)
      - ProviderFactory  (LLM provider creation)
      - FileManager      (physical file operations)
    """

    def __init__(self) -> None:
        self._repo = OcrRepository()
        self._provider_factory = ProviderFactory()
        self._file_manager = FileManager()

    # ─── Public API ───────────────────────────────────────────────

    def create_job(self, zip_path: str, model_name: str) -> str:
        """Create an OCR Job from a ZIP file. Returns the job name."""
        if not os.path.exists(zip_path):
            frappe.throw(f"ZIP file not found: {zip_path}")

        output_path = self._file_manager.build_output_path(zip_path).replace(".zip", "")
        
        # We don't know total_pages until extraction.
        job_name = self._repo.create_job(zip_path, output_path, model_name, 0)

        logger.info("Job %s created from %s", job_name, zip_path)
        return job_name

    def run_job(self, job_name: str, max_workers: int = 3) -> None:
        """Process all pending pages: render → LLM → save. Resumable."""
        job = self._repo.get_job(job_name)
        if job.status == "Completed":
            logger.info("Job %s already completed", job_name)
            return

        self._repo.mark_job_running(job_name)
        logger.info("Job %s started with max_workers=%d", job_name, max_workers)

        # Set up infrastructure
        model_manager = self._setup_model_manager(job.model_name)
        provider = self._provider_factory.create(job.model_name)
        images_dir = self._file_manager.get_images_dir(job.output_path)
        writer = MarkdownWriter(job.output_path)

        # Phase 1: Extract Images
        if job.total_pages == 0:
            self._extract_phase(job, images_dir)
            job = self._repo.get_job(job_name)

        # Re-fetch pending after extraction
        pending = self._repo.get_pending_pages(job_name)
        if not pending:
            logger.info("No pending pages for job %s", job_name)
            return

        # Phase 2: LLM Process
        caller = LlmCaller(provider, job.total_pages, model_manager, job.model_name)
        self._llm_phase(job_name, pending, caller, writer, max_workers)

        # Phase 3: Finalize
        final_status = self._repo.finalize_job(job_name)
        logger.info("Job %s finalized with status: %s", job_name, final_status)

    def get_status(self, job_name: str) -> dict:
        """Return the current status snapshot as a dict."""
        return self._repo.get_job_status(job_name).to_dict()

    def get_output(self, job_name: str) -> str:
        """Return the assembled markdown content."""
        job = self._repo.get_job(job_name)
        writer = MarkdownWriter(job.output_path)
        content = writer.read()
        if content:
            return content
        # Fallback: assemble from DB
        pages = self._repo.get_completed_page_markdowns(job_name)
        return MarkdownWriter.assemble_from_pages(pages)

    def list_jobs(self) -> list[dict]:
        """List all OCR jobs."""
        return self._repo.list_jobs()

    def delete_job(self, job_name: str) -> None:
        """Delete a job, its pages, and physical assets."""
        try:
            job = self._repo.get_job(job_name)
            self._file_manager.cleanup_job_files(
                job.output_path, job.status == "Completed"
            )
        except Exception as e:
            logger.error("File cleanup error: %s", e)
        self._repo.delete_job(job_name)

    def reset_job(self, job_name: str) -> None:
        """Wipe OCR progress but keep rendered images."""
        job = self._repo.get_job(job_name)
        writer = MarkdownWriter(job.output_path)
        writer.delete()
        self._repo.reset_job(job_name)

    def stop_job(self, job_name: str) -> None:
        """Pause a running job (worker will see the status change and exit)."""
        self._repo.mark_job_paused(job_name)

    # ─── Private: Two-Phase Processing ───────────────────────────

    def _extract_phase(self, job, images_dir: str) -> None:
        """Phase 1: Extract all images from the uploaded ZIP file."""
        zip_path = self._file_manager.validate_zip(job.zip_path)
        logger.info("Extracting %s to %s", zip_path, images_dir)
        
        extracted_images = self._file_manager.extract_zip(zip_path, images_dir)
        
        total_pages = len(extracted_images)
        if total_pages == 0:
            frappe.throw("ZIP file contains no valid images.")
            
        job.total_pages = total_pages
        job.save(ignore_permissions=True)
        frappe.db.commit()
        
        self._repo.create_pages(job.name, total_pages)
        
        for p_num, img_path in enumerate(extracted_images, start=1):
            self._repo.set_page_rendering_done(job.name, p_num, img_path)
            
        frappe.db.commit()
        logger.info("Extracted %d images from ZIP", total_pages)

    def _llm_phase(
        self, job_name: str, pending: list[dict],
        caller: LlmCaller, writer: MarkdownWriter, max_workers: int,
    ) -> None:
        """Phase 2: Process the rendered images through the LLM."""
        job = self._repo.get_job(job_name)

        # Process in chunks just to periodically update the UI counters and check for stop
        chunk_size = max_workers
        for i in range(0, len(pending), chunk_size):
            if not self._repo.is_job_active(job_name):
                logger.info("Job %s stopped by user", job_name)
                break

            chunk = pending[i:i + chunk_size]
            self._process_batch(job_name, chunk, caller, writer, max_workers, job.total_pages)
            self._repo.update_job_counters(job_name)

    def _process_batch(
        self, job_name: str, batch: list[dict],
        caller: LlmCaller, writer: MarkdownWriter,
        max_workers: int, total_pages: int,
    ) -> None:
        """Process a single batch of pages through the LLM."""
        # Mark batch as Processing
        self._repo.bulk_set_status([p["name"] for p in batch], STATUS_PROCESSING)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for page_rec in batch:
                page_doc = self._repo.get_page(page_rec["name"])
                if not page_doc.image_path:
                    self._repo.save_page_error(page_rec["name"], "Image not rendered")
                    continue
                future = executor.submit(
                    caller.process_page, page_doc.image_path, page_rec["page_number"]
                )
                futures[future] = page_rec["name"]

            for future in as_completed(futures):
                page_name = futures[future]
                try:
                    result = future.result()
                    self._repo.save_page_result(
                        page_name, result.markdown, result.elapsed_seconds
                    )
                    writer.append_page(result.page_number, result.markdown)
                    logger.info(
                        "Page %d/%d saved (%.1fs)",
                        result.page_number, total_pages, result.elapsed_seconds,
                    )
                except Exception as e:
                    logger.error("Page %s failed: %s", page_name, e)
                    self._repo.save_page_error(page_name, str(e))

        frappe.db.commit()

    # ─── Private: Infrastructure Setup ────────────────────────────

    def _setup_model_manager(self, model_name: str):
        """Set up ModelManager for LMS providers. Returns None for non-LMS."""
        api_root, base_url = self._provider_factory.get_lms_urls()
        if not api_root:
            return None
        manager = ModelManager(api_root, base_url)
        manager.ensure_loaded(model_name)
        return manager
