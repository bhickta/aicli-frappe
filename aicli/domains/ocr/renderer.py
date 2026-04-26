"""
OCR Renderer — Memory-safe PDF page to image conversion.

Designed to prevent OOM crashes on machines with limited RAM:
  - Sequential page rendering (one page at a time, one PDF handle)
  - Explicit pixmap disposal after each page write
  - Small-batch processing with optional parallelism
  - Memory monitoring to detect pressure before the OS kills us
"""

import gc
import os
import logging

logger = logging.getLogger(__name__)

# Hardcoded here (not imported) so subprocess workers don't need package imports
_PAGE_FMT = "page_{:04d}.jpg"

# Maximum pages to render before forcing a garbage collection cycle
_GC_EVERY_N_PAGES = 5

# Memory warning threshold (fraction of total system memory)
_MEMORY_WARN_THRESHOLD = 0.80


def _get_memory_usage_fraction() -> float | None:
    """Return current RSS as a fraction of total system memory, or None if unavailable."""
    try:
        import resource
        rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # KB → bytes on Linux
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_bytes = int(line.split()[1]) * 1024  # KB → bytes
                    return rss_bytes / total_bytes if total_bytes > 0 else None
    except Exception:
        return None
    return None


def _render_single_page(pdf_path: str, images_dir: str, dpi: int, page_number: int) -> tuple[int, str]:
    """
    Render exactly ONE page. Used as a subprocess target when parallel mode is enabled.
    Must be fully self-contained — no relative imports, no frappe, no logger.
    """
    import fitz

    img_path = os.path.join(images_dir, _PAGE_FMT.format(page_number))
    if os.path.isfile(img_path):
        return page_number, img_path

    doc = fitz.open(pdf_path)
    try:
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = doc[page_number - 1].get_pixmap(matrix=mat, alpha=False)
        
        # PyMuPDF's default save creates massive files. 
        # Convert to PIL and compress to drastically reduce size.
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img.save(img_path, "JPEG", quality=85, optimize=True)
        
        del img
        del pix  # Release pixel buffer immediately
    finally:
        doc.close()

    return page_number, img_path


class PdfRenderer:
    """Renders PDF pages to images with memory-safe sequential processing.

    By default, renders pages sequentially in the current process to avoid
    multiplying memory usage across workers. Parallel mode is available but
    uses strict per-page subprocess isolation (one fitz.open per page) to
    contain memory.
    """

    # Batch size for sequential rendering before forcing GC
    BATCH_SIZE = 10

    def __init__(self, pdf_path: str, images_dir: str, dpi: int) -> None:
        self._pdf_path = os.path.abspath(pdf_path)
        self._images_dir = os.path.abspath(images_dir) if images_dir else ""
        self._dpi = dpi

    def ensure_output_dir(self) -> None:
        if self._images_dir:
            os.makedirs(self._images_dir, exist_ok=True)

    def count_pages(self) -> int:
        import fitz
        doc = fitz.open(self._pdf_path)
        count = len(doc)
        doc.close()
        return count

    def render_pages(
        self, page_numbers: list[int], max_workers: int | None = None,
    ) -> dict[int, str]:
        """
        Render requested pages to images.

        Defaults to parallel rendering with per-page process isolation.
        Each subprocess opens the PDF, renders ONE page, frees it, and exits.
        Peak memory = max_workers × (~15 MB pixmap + mmap'd PDF).
        Falls back to sequential if max_workers=1.
        """
        if not page_numbers:
            return {}

        self.ensure_output_dir()

        # Pre-filter: skip already-rendered pages
        to_render = []
        cached: dict[int, str] = {}
        for p_num in page_numbers:
            img_path = os.path.join(self._images_dir, _PAGE_FMT.format(p_num))
            if os.path.isfile(img_path):
                cached[p_num] = img_path
            else:
                to_render.append(p_num)

        if cached:
            logger.info("Cache hit: %d/%d pages already rendered", len(cached), len(page_numbers))

        if not to_render:
            return cached

        from multiprocessing import cpu_count
        effective_workers = max_workers if max_workers and max_workers >= 1 else (cpu_count() or 4)

        if effective_workers > 1 and len(to_render) > 1:
            results = self._render_parallel(to_render, effective_workers)
        else:
            results = self._render_sequential(to_render)

        results.update(cached)
        logger.info("Rendering done: %d pages total", len(results))
        return results

    def _render_sequential(self, page_numbers: list[int]) -> dict[int, str]:
        """Render pages one-at-a-time in the current process. Minimal memory footprint."""
        import fitz

        logger.info(
            "Rendering %d pages sequentially (dpi=%d, pdf=%s)",
            len(page_numbers), self._dpi, os.path.basename(self._pdf_path),
        )

        doc = fitz.open(self._pdf_path)
        zoom = self._dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        results: dict[int, str] = {}

        try:
            for i, p_num in enumerate(page_numbers, start=1):
                img_path = os.path.join(self._images_dir, _PAGE_FMT.format(p_num))

                pix = doc[p_num - 1].get_pixmap(matrix=mat, alpha=False)
                pix.save(img_path)
                # Explicitly release the pixmap to free memory immediately.
                # Without this, Python may defer GC and accumulate hundreds of MBs.
                del pix
                results[p_num] = img_path

                # Periodic GC to reclaim any lingering buffers
                if i % _GC_EVERY_N_PAGES == 0:
                    gc.collect()

                # Memory pressure check every batch
                if i % self.BATCH_SIZE == 0:
                    mem_frac = _get_memory_usage_fraction()
                    if mem_frac and mem_frac > _MEMORY_WARN_THRESHOLD:
                        logger.warning(
                            "Memory usage %.0f%% after %d/%d pages — forcing GC",
                            mem_frac * 100, i, len(page_numbers),
                        )
                        gc.collect()

                    logger.info("Rendered %d/%d pages", i, len(page_numbers))
        finally:
            doc.close()

        return results

    def _render_parallel(self, page_numbers: list[int], max_workers: int) -> dict[int, str]:
        """Render pages in parallel subprocesses — one page per task for memory isolation.

        Each task calls _render_single_page which:
          1. Opens the PDF (mmap'd, lightweight)
          2. Renders exactly ONE page to a pixmap
          3. Saves to disk, del pix, closes PDF
          4. Returns — subprocess memory fully reclaimed

        Peak memory = max_workers × (~15 MB pixmap + mmap'd PDF handle).
        """
        from concurrent.futures import ProcessPoolExecutor, as_completed

        workers = min(max_workers, len(page_numbers))

        logger.info(
            "Rendering %d pages across %d workers (dpi=%d, pdf=%s)",
            len(page_numbers), workers, self._dpi, os.path.basename(self._pdf_path),
        )

        results: dict[int, str] = {}
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _render_single_page, self._pdf_path, self._images_dir, self._dpi, p_num
                ): p_num
                for p_num in page_numbers
            }
            for future in as_completed(futures):
                try:
                    p_num, img_path = future.result()
                    results[p_num] = img_path
                except Exception as e:
                    p_num = futures[future]
                    logger.error("Failed to render page %d: %s", p_num, e)

        logger.info("Parallel rendering complete: %d pages", len(results))
        return results
