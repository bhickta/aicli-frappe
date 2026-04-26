"""
OCR Job Service — Thin orchestrator that ties all domain components together.

This is the only class that composes the other components.
Each method is a high-level use case with clear logging and error handling.
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import frappe

from .constants import STATUS_RENDERING, STATUS_PROCESSING
from .repository import OcrRepository
from .renderer import PdfRenderer
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
      - PdfRenderer     (PDF → images)
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

    def create_job(self, pdf_path: str, model_name: str, dpi: int = 200) -> str:
        """Create an OCR Job with all its page records. Returns the job name."""
        abs_path = self._file_manager.validate_pdf(pdf_path)
        output_path = self._file_manager.build_output_path(abs_path)

        renderer = PdfRenderer(abs_path, "", dpi)
        total_pages = renderer.count_pages()
        if total_pages == 0:
            frappe.throw("PDF has zero pages.")

        job_name = self._repo.create_job(abs_path, output_path, model_name, total_pages, dpi)
        self._repo.create_pages(job_name, total_pages)

        logger.info("Job %s created — %d pages from %s", job_name, total_pages, abs_path)
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

        # Get pending pages
        pending = self._repo.get_pending_pages(job_name)
        if not pending:
            logger.info("No pending pages for job %s", job_name)
            return

        # Phase 1: Render all pages
        self._render_phase(job, pending, images_dir, max_workers)

        # Phase 2: LLM processing in batches
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

    # ─── Private: Render Phase ────────────────────────────────────

    def _render_phase(self, job, pending: list[dict], images_dir: str, max_workers: int) -> None:
        """Render all pending pages to images."""
        page_names = [p["name"] for p in pending]
        self._repo.bulk_set_status(page_names, STATUS_RENDERING)

        page_numbers = [p["page_number"] for p in pending]
        renderer = PdfRenderer(job.pdf_path, images_dir, job.dpi)
        results = renderer.render_pages(page_numbers, max_workers)

        for p_num, img_path in results.items():
            self._repo.set_page_rendering_done(job.name, p_num, img_path)
        frappe.db.commit()
        logger.info("Render phase complete: %d/%d pages", len(results), len(pending))

    # ─── Private: LLM Phase ──────────────────────────────────────

    def _llm_phase(
        self, job_name: str, pending: list[dict],
        caller: LlmCaller, writer: MarkdownWriter, max_workers: int,
    ) -> None:
        """Process pages through LLM in batches with stop-check between batches."""
        job = self._repo.get_job(job_name)

        for i in range(0, len(pending), max_workers):
            # Check for user-initiated stop
            if not self._repo.is_job_active(job_name):
                logger.info("Job %s stopped by user, exiting", job_name)
                break

            batch = pending[i:i + max_workers]
            self._process_batch(job_name, batch, caller, writer, max_workers, job.total_pages)

            # Update counters after each batch
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
