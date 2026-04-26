"""
OCR Renderer — High-performance PDF page to image conversion.

Optimized for speed:
  - ProcessPoolExecutor for true CPU parallelism (bypasses GIL)
  - Large chunk sizes to amortize PDF open/close overhead
  - File-existence caching to skip already-rendered pages
  - Auto-detects CPU count for optimal worker allocation
"""

import os
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

import fitz  # PyMuPDF
import PIL.Image

from .constants import PAGE_IMAGE_FORMAT

# Disable PIL decompression bomb limit for high-DPI PDF pages
PIL.Image.MAX_IMAGE_PIXELS = None

logger = logging.getLogger(__name__)


def _render_chunk(pdf_path: str, images_dir: str, dpi: int, page_numbers: list[int]) -> dict[int, str]:
    """
    Render a chunk of pages from a single PDF handle.
    Runs in a separate PROCESS for true parallelism.
    Returns {page_number: image_path}.
    """
    results = {}
    try:
        doc = fitz.open(pdf_path)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        for p_num in page_numbers:
            img_path = os.path.join(images_dir, PAGE_IMAGE_FORMAT.format(p_num))

            # Cache: skip if image already exists
            if os.path.isfile(img_path):
                results[p_num] = img_path
                continue

            page = doc[p_num - 1]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pix.save(img_path)
            results[p_num] = img_path

        doc.close()
    except Exception as e:
        # Log to stderr since logger may not be configured in subprocess
        import traceback
        traceback.print_exc()
    return results


class PdfRenderer:
    """Renders PDF pages to PNG images with process-based parallelism and caching."""

    # Minimum pages per worker to amortize PDF open/close overhead
    MIN_PAGES_PER_WORKER = 20

    def __init__(self, pdf_path: str, images_dir: str, dpi: int) -> None:
        self._pdf_path = os.path.abspath(pdf_path)
        self._images_dir = os.path.abspath(images_dir) if images_dir else ""
        self._dpi = dpi

    def ensure_output_dir(self) -> None:
        """Create the images output directory if it doesn't exist."""
        if self._images_dir:
            os.makedirs(self._images_dir, exist_ok=True)

    def count_pages(self) -> int:
        """Return the total number of pages in the PDF."""
        doc = fitz.open(self._pdf_path)
        count = len(doc)
        doc.close()
        return count

    def render_pages(
        self, page_numbers: list[int], max_workers: int | None = None,
    ) -> dict[int, str]:
        """
        Render the given page numbers using ProcessPoolExecutor.

        Uses true OS-level parallelism (no GIL) for maximum throughput.
        Auto-tunes worker count based on CPU cores and page count.
        Skips pages whose image already exists on disk (caching).
        """
        if not page_numbers:
            return {}

        self.ensure_output_dir()

        # Filter out already-rendered pages before spawning processes
        to_render = []
        cached: dict[int, str] = {}
        for p_num in page_numbers:
            img_path = os.path.join(self._images_dir, PAGE_IMAGE_FORMAT.format(p_num))
            if os.path.isfile(img_path):
                cached[p_num] = img_path
            else:
                to_render.append(p_num)

        if cached:
            logger.info("Skipping %d already-rendered pages (cached)", len(cached))

        if not to_render:
            return cached

        # Auto-tune workers: use all CPUs, but cap by page count
        cpus = cpu_count() or 4
        effective_workers = max_workers or cpus
        effective_workers = min(effective_workers, cpus, len(to_render))
        # Ensure each worker gets enough pages to amortize overhead
        effective_workers = max(1, min(
            effective_workers,
            len(to_render) // self.MIN_PAGES_PER_WORKER or 1,
        ))

        chunks = self._split_into_chunks(to_render, effective_workers)

        logger.info(
            "Rendering %d pages with %d processes (pdf=%s, dpi=%d)",
            len(to_render), len(chunks), os.path.basename(self._pdf_path), self._dpi,
        )

        all_results = dict(cached)
        with ProcessPoolExecutor(max_workers=len(chunks)) as executor:
            futures = {
                executor.submit(
                    _render_chunk, self._pdf_path, self._images_dir, self._dpi, chunk
                ): chunk
                for chunk in chunks
            }
            for future in as_completed(futures):
                try:
                    chunk_results = future.result()
                    all_results.update(chunk_results)
                    logger.info("Rendered chunk: %d pages", len(chunk_results))
                except Exception as e:
                    logger.error("Chunk rendering failed: %s", e)

        logger.info(
            "Rendering complete: %d/%d pages (%.0f%% cached)",
            len(all_results), len(page_numbers),
            len(cached) / len(page_numbers) * 100 if page_numbers else 0,
        )
        return all_results

    @staticmethod
    def _split_into_chunks(items: list, num_chunks: int) -> list[list]:
        """Split a list into approximately equal chunks."""
        chunk_size = max(1, len(items) // num_chunks)
        chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
        return chunks
