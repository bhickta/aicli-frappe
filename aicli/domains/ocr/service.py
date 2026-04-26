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
OCR_SYSTEM_PROMPT = "You are a professional document digitizer. Output valid Markdown only."

# ─── Per-Page Prompt ──────────────────────────────────────────────
OCR_PAGE_PROMPT_TEMPLATE = """You are a high-precision OCR engine.
Extract ALL text from this image (Page {page_number}/{total_pages}).

RULES:
1. Output ONLY the extracted text in Markdown. No preamble.
2. Preserve structure: # Headings, - Lists, | Tables |, **Bold**, *Italic*.
3. For images/photos, use placeholder: <<page_{page_number}_image_N>>
4. Maintain natural reading order.
5. Do NOT repeat these instructions in the output."""


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
            self._ensure_model_loaded(api_root, base_url, job.model_name)
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

        if not pending_pages:
            logger.info("No pending pages for job %s", job_name)
            return

        # 1) Massive Bulk Render (Parallel)
        logger.info("Bulk rendering %d pages for job %s...", len(pending_pages), job_name)
        def bulk_render(p_num):
            try:
                t_pdf = fitz.open(job.pdf_path)
                path = self._render_page(t_pdf, p_num, images_dir, job.dpi)
                t_pdf.close()
                return p_num, path
            except Exception as e:
                logger.error("Bulk render failed for page %d: %s", p_num, e)
                return p_num, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
            render_results = dict(executor.map(bulk_render, [p["page_number"] for p in pending_pages]))

        # Update DB with image paths
        for page_rec in pending_pages:
            p_num = page_rec["page_number"]
            if render_results.get(p_num):
                frappe.db.set_value("OCR Page", page_rec["name"], "image_path", render_results[p_num], update_modified=False)
        frappe.db.commit()

        # 2) Process LLM calls in batches
        for i in range(0, len(pending_pages), max_workers):
            # ── Check for user-initiated stop ──
            job.reload()
            if job.status not in ["Running", "Queued"]:
                logger.info("OCR Job %s was stopped by user. Exiting worker loop.", job_name)
                break

            batch = pending_pages[i : i + max_workers]

            # Mark batch as Processing
            for page_rec in batch:
                frappe.db.set_value("OCR Page", page_rec["name"], "status", "Processing", update_modified=False)
            frappe.db.commit()

            def call_llm(p_name, p_num):
                page_doc = frappe.get_doc("OCR Page", p_name)
                if not page_doc.image_path:
                    raise Exception("Image not rendered")

                prompt = OCR_PAGE_PROMPT_TEMPLATE.format(page_number=p_num, total_pages=job.total_pages)
                start_t = time.perf_counter()

                max_attempts = 5
                for attempt in range(max_attempts):
                    try:
                        markdown = provider.describe_image(
                            image_path=page_doc.image_path,
                            prompt=prompt,
                            system_prompt=OCR_SYSTEM_PROMPT,
                            max_size=1536,
                            temperature=0.0,
                            max_tokens=1500,
                            max_retries=1,
                        )
                        return p_num, markdown, time.perf_counter() - start_t
                    except Exception as e:
                        error_str = str(e)
                        if hasattr(e, "response") and hasattr(e.response, "text"):
                            error_str += f" | {e.response.text}"

                        if "model has crashed" in error_str.lower() or "channel error" in error_str.lower():
                            if attempt < max_attempts - 1:
                                self._unload_model_via_api(api_root, job.model_name)
                                time.sleep(2)
                                self._load_model_via_api(api_root, job.model_name)
                                time.sleep(5)
                                continue
                        
                        if attempt < max_attempts - 1:
                            time.sleep((2 ** attempt) + random.uniform(0.5, 1.0))
                        else:
                            raise Exception(error_str)

            futures = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                for page_rec in batch:
                    futures[executor.submit(call_llm, page_rec["name"], page_rec["page_number"])] = page_rec["name"]

            # 3) Save results
            for future in concurrent.futures.as_completed(futures):
                page_name = futures[future]
                page_doc = frappe.get_doc("OCR Page", page_name)
                try:
                    p_num, markdown, elapsed = future.result()
                    page_doc.markdown_output = markdown
                    page_doc.processing_time = round(elapsed, 2)
                    page_doc.status = "Completed"
                    logger.info("OCR page %d/%d done in %.1fs — job %s", p_num, job.total_pages, elapsed, job_name)
                except Exception as e:
                    logger.error("OCR page %s failed: %s", page_doc.page_number, e)
                    page_doc.status = "Failed"
                    page_doc.error = str(e)[:2000]
                page_doc.save(ignore_permissions=True)
            frappe.db.commit()

            # 4) Update job counters & markdown
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
        """Delete a job, its pages, and all physical assets."""
        try:
            job = frappe.get_doc("OCR Job", job_name)
            
            # 1) Physical cleanup
            if job.output_path:
                # Delete the markdown file
                if os.path.exists(job.output_path):
                    os.remove(job.output_path)
                
                # Delete the images directory
                images_dir = os.path.join(os.path.dirname(job.output_path), "images")
                if os.path.exists(images_dir):
                    import shutil
                    shutil.rmtree(images_dir)
                    logger.info("Deleted assets directory: %s", images_dir)

            # 2) Database cleanup
            frappe.db.delete("OCR Page", {"ocr_job": job_name})
            frappe.delete_doc("OCR Job", job_name, ignore_permissions=True)
            frappe.db.commit()
            logger.info("Deleted OCR Job records for: %s", job_name)
        except Exception as e:
            logger.error("Error during job deletion: %s", e)
            # Still try to delete from DB if file cleanup fails
            frappe.db.delete("OCR Page", {"ocr_job": job_name})
            frappe.delete_doc("OCR Job", job_name, ignore_permissions=True, ignore_missing=True)
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

    def _ensure_model_loaded(self, api_root: str, base_url: str, model_name: str) -> None:
        """Check if model is already loaded in LM Studio. Only load if missing.
        This preserves user's manual settings (parallel count, KV cache, etc.)."""
        import requests
        try:
            res = requests.get(f"{base_url}/models", timeout=10)
            if res.ok:
                loaded_ids = [m["id"] for m in res.json().get("data", [])]
                if model_name in loaded_ids:
                    logger.info("Model %s is already loaded. Skipping reload to preserve settings.", model_name)
                    return
        except Exception as e:
            logger.warning("Could not check loaded models: %s", e)
        # Model not loaded — load it via API
        self._load_model_via_api(api_root, model_name)

    def _load_model_via_api(self, api_root: str, model_name: str) -> None:
        """Load a model into LM Studio via the REST API with optimal settings.
        Note: n_parallel is NOT available via the API — set it in the LM Studio UI."""
        import requests
        url = f"{api_root}/api/v1/models/load"
        payload = {
            "model": model_name,
            "context_length": 32768,
            "flash_attention": True,
            "offload_kv_cache_to_gpu": False,
            "eval_batch_size": 512,
            "echo_load_config": True,
        }
        logger.info("Loading model %s via LM Studio API at %s...", model_name, url)
        try:
            res = requests.post(url, json=payload, timeout=120)
            if res.ok:
                data = res.json()
                logger.info("Model loaded: %s", data)
            else:
                logger.error("Failed to load model via API: %s %s", res.status_code, res.text)
        except Exception as e:
            logger.error("LM Studio API load request failed: %s", e)

    def _unload_model_via_api(self, api_root: str, model_name: str) -> None:
        """Unload a model from LM Studio via the REST API."""
        import requests
        url = f"{api_root}/api/v1/models/unload"
        payload = {"instance_id": model_name}
        logger.info("Unloading model %s via LM Studio API...", model_name)
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.ok:
                logger.info("Model unloaded: %s", res.json())
            else:
                logger.warning("Unload response: %s %s", res.status_code, res.text)
        except Exception as e:
            logger.error("LM Studio API unload request failed: %s", e)

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
