"""
LLM-Powered PDF → Markdown OCR Service.

Converts PDF pages to images, sends each to a vision-capable LLM,
and assembles the results into a clean Markdown document.
Saves after every page for progress tracking and resume capability.
"""

import os
import time
import logging
import fitz  # PyMuPDF
import PIL.Image
from pathlib import Path
from typing import Optional

# Disable PIL's decompression bomb limit for large, high-dpi PDF pages
PIL.Image.MAX_IMAGE_PIXELS = None

import frappe
from frappe.utils import now_datetime

logger = logging.getLogger(__name__)

# ─── System Prompt ────────────────────────────────────────────────
OCR_SYSTEM_PROMPT = """You are a world-class OCR engine. Your job is to convert a scanned document page image into clean, faithful Markdown text."""

# ─── Per-Page Prompt ──────────────────────────────────────────────
OCR_PAGE_PROMPT_TEMPLATE = """Convert this scanned page (page {page_number} of {total_pages}) to clean Markdown.

## Rules — follow ALL of them strictly:

1. **Extract ALL text faithfully.** Do not summarize, skip, or rephrase anything. Every word on the page must appear in your output.
2. **Preserve structure.** Use proper Markdown:
   - `#`, `##`, `###` for headings (match the visual hierarchy)
   - `-` or `1.` for lists
   - `| col | col |` for tables (with header separator `|---|---|`)
   - `**bold**`, `*italic*` where the original uses them
   - `> ` for blockquotes
   - ``` for code blocks
3. **Diagrams and flowcharts:** If you can represent it as ASCII art or a textual description, do so inside a fenced code block. Example:
   ```
   [Start] --> [Process A] --> [Decision?]
                                 |
                            Yes / \\ No
                           [B]   [C]
   ```
4. **Images containing readable text** (signs, labels, captions, handwritten notes): Extract the text.
5. **Photographs or complex images** that cannot be meaningfully converted to text: Insert a placeholder reference exactly like this: `<<page_{page_number}_image_N>>` where N is the image sequence number on this page (1, 2, 3…).
6. **Reading order:** Follow the natural reading order (left-to-right, top-to-bottom). For multi-column layouts, process column by column.
7. **Output ONLY the Markdown.** No preamble, no explanations, no "Here is the markdown:" prefix. Start directly with the content."""


class OcrService:
    """Stateless service — all state lives in the OCR Job / OCR Page DocTypes."""

    # ── Public API ────────────────────────────────────────────────

    def create_job(self, pdf_path: str, model_name: str, dpi: int = 200) -> str:
        """
        Create an OCR Job record and its child OCR Page records.
        Returns the job name (ID).
        """
        pdf_path = os.path.abspath(pdf_path)
        if not os.path.isfile(pdf_path):
            frappe.throw(f"PDF file not found: {pdf_path}")

        # Count pages via PyMuPDF
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        doc.close()

        if total_pages == 0:
            frappe.throw("PDF has zero pages.")

        # Derive output path: same dir, same name but .md
        stem = Path(pdf_path).stem
        output_dir = os.path.join(
            frappe.get_site_path("public", "files", "aicli_ocr"),
            stem,
        )
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{stem}.md")

        # Create job
        job = frappe.get_doc({
            "doctype": "OCR Job",
            "pdf_path": pdf_path,
            "output_path": output_path,
            "model_name": model_name,
            "status": "Queued",
            "total_pages": total_pages,
            "completed_pages": 0,
            "failed_pages": 0,
            "dpi": dpi,
        })
        job.insert(ignore_permissions=True)

        # Create one OCR Page per page
        for pg in range(1, total_pages + 1):
            frappe.get_doc({
                "doctype": "OCR Page",
                "ocr_job": job.name,
                "page_number": pg,
                "status": "Pending",
            }).insert(ignore_permissions=True)

        frappe.db.commit()
        logger.info("OCR job %s created — %d pages from %s", job.name, total_pages, pdf_path)
        return job.name

    def run_job(self, job_name: str, max_workers: int = 1) -> None:
        """
        Process all pending pages for the given job.
        Pages are processed strictly one at a time to avoid GPU KV cache exhaustion.
        Saves after every page so progress is visible and the job is resumable.
        """
        import random

        job = frappe.get_doc("OCR Job", job_name)
        if job.status == "Completed":
            return

        job.status = "Running"
        job.started_at = job.started_at or now_datetime()
        job.save(ignore_permissions=True)
        frappe.db.commit()

        doc = frappe.get_single("AICLI Settings")
        if doc.provider_type in ["lms", "lmstudio"]:
            base_url = (doc.get("lms_base_url") or doc.get("lm_studio_base_url") or "http://localhost:1234/v1").rstrip("/")
            # Strip /v1 to get the root URL for the management API
            api_root = base_url.replace("/v1", "")
            self._load_model_via_api(api_root, job.model_name)
        provider = self._get_provider(job.model_name)
        pdf_doc = fitz.open(job.pdf_path)
        images_dir = os.path.join(os.path.dirname(job.output_path), "images")
        os.makedirs(images_dir, exist_ok=True)

        # Get pending pages (for resume)
        pending_pages = frappe.get_all(
            "OCR Page",
            filters={"ocr_job": job_name, "status": ["in", ["Pending", "Failed", "Processing"]]},
            fields=["name", "page_number"],
            order_by="page_number asc",
        )

        for page_rec in pending_pages:
            # ── Check for user-initiated stop ──
            job.reload()
            if job.status not in ["Running", "Queued"]:
                logger.info("OCR Job %s was stopped by user. Exiting worker loop.", job_name)
                break

            page_doc = frappe.get_doc("OCR Page", page_rec["name"])
            page_doc.status = "Processing"

            # 1) Render page image
            try:
                img_path = self._render_page(pdf_doc, page_rec["page_number"], images_dir, job.dpi)
                page_doc.image_path = img_path
            except Exception as e:
                page_doc.status = "Failed"
                page_doc.error = f"Render failed: {str(e)[:1000]}"
                page_doc.save(ignore_permissions=True)
                frappe.db.commit()
                continue
            page_doc.save(ignore_permissions=True)
            frappe.db.commit()

            # 2) Call LLM — sequential, one page at a time
            prompt = OCR_PAGE_PROMPT_TEMPLATE.format(
                page_number=page_rec["page_number"], total_pages=job.total_pages
            )
            start_t = time.perf_counter()
            max_attempts = 5
            success = False

            for attempt in range(max_attempts):
                try:
                    markdown = provider.describe_image(
                        image_path=img_path,
                        prompt=prompt,
                        system_prompt=OCR_SYSTEM_PROMPT,
                        max_size=1536,
                        temperature=0.0,
                        max_tokens=1500,
                        max_retries=1,
                    )
                    elapsed = time.perf_counter() - start_t
                    page_doc.markdown_output = markdown
                    page_doc.processing_time = round(elapsed, 2)
                    page_doc.status = "Completed"
                    logger.info(
                        "OCR page %d/%d done in %.1fs — job %s",
                        page_rec["page_number"], job.total_pages, elapsed, job_name,
                    )
                    success = True
                    break
                except Exception as e:
                    error_str = str(e)
                    if hasattr(e, "response") and hasattr(e.response, "text"):
                        error_str += f" | {e.response.text}"

                    is_crash = (
                        "model has crashed" in error_str.lower()
                        or "channel error" in error_str.lower()
                        or "failed to process image" in error_str.lower()
                    )

                    if attempt < max_attempts - 1:
                        if is_crash:
                            import subprocess
                            logger.error(
                                "Model crashed on page %d! Attempting to revive %s...",
                                page_rec["page_number"], job.model_name,
                            )
                            subprocess.run(["lms", "unload", "--all"], capture_output=True)
                            time.sleep(3)
                            subprocess.run(["lms", "load", job.model_name], capture_output=True)
                            sleep_time = 5.0
                        else:
                            sleep_time = (2 ** attempt) + random.uniform(0.5, 2.0)

                        logger.warning(
                            "OCR page %d LLM call failed (%s), retrying in %.1fs...",
                            page_rec["page_number"], error_str, sleep_time,
                        )
                        time.sleep(sleep_time)
                    else:
                        logger.error(
                            "OCR page %d failed after %d attempts: %s",
                            page_rec["page_number"], max_attempts, error_str,
                        )

            if not success:
                page_doc.status = "Failed"
                page_doc.error = error_str[:2000]

            page_doc.save(ignore_permissions=True)
            frappe.db.commit()

            # 3) Update job counters & markdown after every page
            job.reload()
            job.completed_pages = frappe.db.count("OCR Page", {"ocr_job": job_name, "status": "Completed"})
            job.failed_pages = frappe.db.count("OCR Page", {"ocr_job": job_name, "status": "Failed"})
            job.save(ignore_permissions=True)
            frappe.db.commit()

            self._write_markdown(job_name, job.output_path)

        pdf_doc.close()

        # Final status
        job.reload()
        remaining = frappe.db.count(
            "OCR Page", {"ocr_job": job_name, "status": ["in", ["Pending", "Processing"]]}
        )
        if remaining == 0:
            job.status = "Completed" if job.failed_pages == 0 else "Failed"
            job.completed_at = now_datetime()
        else:
            job.status = "Paused"
        job.save(ignore_permissions=True)
        frappe.db.commit()

    def get_status(self, job_name: str) -> dict:
        """Return the current status of a job."""
        job = frappe.get_doc("OCR Job", job_name)
        pages = frappe.get_all(
            "OCR Page",
            filters={"ocr_job": job_name},
            fields=["page_number", "status", "processing_time", "error"],
            order_by="page_number asc",
        )
        return {
            "name": job.name,
            "pdf_path": job.pdf_path,
            "output_path": job.output_path,
            "model_name": job.model_name,
            "status": job.status,
            "total_pages": job.total_pages,
            "completed_pages": job.completed_pages,
            "failed_pages": job.failed_pages,
            "dpi": job.dpi,
            "started_at": str(job.started_at) if job.started_at else None,
            "completed_at": str(job.completed_at) if job.completed_at else None,
            "pages": pages,
        }

    def get_output(self, job_name: str) -> str:
        """Return the assembled markdown content."""
        job = frappe.get_doc("OCR Job", job_name)
        if job.output_path and os.path.isfile(job.output_path):
            with open(job.output_path, "r", encoding="utf-8") as f:
                return f.read()
        # Fallback: assemble from DB
        return self._assemble_markdown(job_name)

    def list_jobs(self) -> list[dict]:
        """List all OCR jobs."""
        return frappe.get_all(
            "OCR Job",
            fields=[
                "name", "pdf_path", "model_name", "status",
                "total_pages", "completed_pages", "failed_pages",
                "started_at", "completed_at",
            ],
            order_by="creation desc",
        )

    def delete_job(self, job_name: str) -> None:
        """Delete a job and all its pages."""
        # Delete page records
        frappe.db.delete("OCR Page", {"ocr_job": job_name})
        # Delete job
        frappe.delete_doc("OCR Job", job_name, ignore_permissions=True)
        frappe.db.commit()

    # ── Private Helpers ───────────────────────────────────────────

    def _get_provider(self, model_name: str):
        """Build a LangChain provider for the given model, using the configured provider type."""
        doc = frappe.get_single("AICLI Settings")
        provider_type = doc.provider_type or "ollama"

        if provider_type in ["lms", "lmstudio"]:
            from langchain_openai import ChatOpenAI
            from aicli.providers.base import LangChainProvider
            base_url = doc.get("lms_base_url") or doc.get("lm_studio_base_url") or "http://localhost:1234/v1"
            api_key = doc.get("lms_api_key") or doc.get("lm_studio_api_key") or "lms"
            llm = ChatOpenAI(base_url=base_url, api_key=api_key, model=model_name)
            return LangChainProvider(llm)
        else:
            from langchain_ollama import ChatOllama
            from aicli.providers.base import LangChainProvider
            base_url = doc.ollama_base_url or "http://localhost:11434"
            llm = ChatOllama(base_url=base_url, model=model_name)
            return LangChainProvider(llm)

    def _render_page(self, pdf_doc, page_num: int, images_dir: str, dpi: int) -> str:
        """Render a single PDF page to a PNG image. Returns the file path."""
        page = pdf_doc[page_num - 1]  # 0-indexed
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_path = os.path.join(images_dir, f"page_{page_num:04d}.png")
        pix.save(img_path)
        return img_path

    def _assemble_markdown(self, job_name: str) -> str:
        """Assemble all completed pages into a single markdown string."""
        pages = frappe.get_all(
            "OCR Page",
            filters={"ocr_job": job_name, "status": "Completed"},
            fields=["page_number", "markdown_output"],
            order_by="page_number asc",
        )
        parts = []
        for p in pages:
            parts.append(f"<!-- Page {p['page_number']} -->\n")
            parts.append(p["markdown_output"] or "")
            parts.append("\n\n---\n\n")
        return "".join(parts)

    def _write_markdown(self, job_name: str, output_path: str) -> None:
        """Write the current assembled markdown to disk."""
        md = self._assemble_markdown(job_name)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md)
