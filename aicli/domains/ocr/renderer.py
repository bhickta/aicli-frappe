"""
OCR Renderer — High-performance PDF page to image conversion.

Optimized for speed:
  - ProcessPoolExecutor for true CPU parallelism (bypasses GIL)
  - Self-contained worker function (no relative imports for subprocess safety)
  - PPM format (zero compression — instant disk writes)
  - File-existence caching to skip already-rendered pages
  - Auto-detects CPU count for optimal worker allocation
"""

import os
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

import PIL.Image

# Disable PIL decompression bomb limit for high-DPI PDF pages
PIL.Image.MAX_IMAGE_PIXELS = None

logger = logging.getLogger(__name__)

# Hardcoded here (not imported) so subprocess workers don't need package imports
_PAGE_FMT = "page_{:04d}.jpg"


def _render_chunk(pdf_path: str, images_dir: str, dpi: int, page_numbers: list[int]) -> dict[int, str]:
    """
    Render a chunk of pages. Runs in a SEPARATE PROCESS.
    Must be fully self-contained — no relative imports, no frappe, no logger.
    """
    import fitz  # import inside function so subprocess doesn't need parent's imports

    results = {}
    try:
        doc = fitz.open(pdf_path)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        for p_num in page_numbers:
            img_path = os.path.join(images_dir, _PAGE_FMT.format(p_num))
            if os.path.isfile(img_path):
                results[p_num] = img_path
                continue

            pix = doc[p_num - 1].get_pixmap(matrix=mat, alpha=False)
            pix.save(img_path)
            results[p_num] = img_path

        doc.close()
    except Exception:
        import traceback
        traceback.print_exc()
    return results


class PdfRenderer:
    """Renders PDF pages to images with process-based parallelism and caching."""

    MIN_PAGES_PER_WORKER = 50

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
        Render pages using ProcessPoolExecutor for true CPU parallelism.
        Pre-filters cached pages. Auto-tunes worker count.
        """
        if not page_numbers:
            return {}

        self.ensure_output_dir()

        # Pre-filter: skip already-rendered pages BEFORE spawning processes
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

        # Auto-tune: use all CPUs, ensure enough pages per worker
        cpus = cpu_count() or 4
        workers = min(max_workers or cpus, cpus, len(to_render))
        workers = max(1, min(workers, len(to_render) // self.MIN_PAGES_PER_WORKER or 1))

        chunks = self._split_chunks(to_render, workers)

        logger.info(
            "Rendering %d pages across %d processes (dpi=%d, pdf=%s)",
            len(to_render), len(chunks), self._dpi, os.path.basename(self._pdf_path),
        )

        all_results = dict(cached)
        with ProcessPoolExecutor(max_workers=len(chunks)) as executor:
            futures = {
                executor.submit(_render_chunk, self._pdf_path, self._images_dir, self._dpi, c): c
                for c in chunks
            }
            for future in as_completed(futures):
                try:
                    all_results.update(future.result())
                except Exception as e:
                    logger.error("Chunk failed: %s", e)

        logger.info("Rendering done: %d pages total", len(all_results))
        return all_results

    @staticmethod
    def _split_chunks(items: list, n: int) -> list[list]:
        size = max(1, len(items) // n)
        return [items[i:i + size] for i in range(0, len(items), size)]
