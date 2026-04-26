"""
OCR Renderer — PDF page to image conversion with caching.

Responsibilities:
  - Render PDF pages to PNG images using PyMuPDF.
  - Skip already-rendered pages (cache by file existence).
  - Support parallel rendering via ThreadPoolExecutor.
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz  # PyMuPDF
import PIL.Image

from .constants import PAGE_IMAGE_FORMAT

# Disable PIL decompression bomb limit for high-DPI PDF pages
PIL.Image.MAX_IMAGE_PIXELS = None

logger = logging.getLogger(__name__)


def _render_chunk(pdf_path: str, images_dir: str, dpi: int, page_numbers: list[int]) -> dict[int, str]:
    """Render a chunk of pages from a single PDF handle. Returns {page_number: image_path}."""
    results = {}
    try:
        doc = fitz.open(pdf_path)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        for p_num in page_numbers:
            img_path = os.path.join(images_dir, PAGE_IMAGE_FORMAT.format(p_num))

            # Cache: skip if image already exists
            if os.path.isfile(img_path):
                logger.debug("Page %d already rendered, skipping", p_num)
                results[p_num] = img_path
                continue

            page = doc[p_num - 1]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pix.save(img_path)
            results[p_num] = img_path

        doc.close()
    except Exception as e:
        logger.error("Rendering chunk failed for %s: %s", pdf_path, e, exc_info=True)
    return results


class PdfRenderer:
    """Renders PDF pages to PNG images with parallel processing and caching."""

    def __init__(self, pdf_path: str, images_dir: str, dpi: int) -> None:
        self._pdf_path = os.path.abspath(pdf_path)
        self._images_dir = os.path.abspath(images_dir)
        self._dpi = dpi

    def ensure_output_dir(self) -> None:
        """Create the images output directory if it doesn't exist."""
        os.makedirs(self._images_dir, exist_ok=True)

    def count_pages(self) -> int:
        """Return the total number of pages in the PDF."""
        doc = fitz.open(self._pdf_path)
        count = len(doc)
        doc.close()
        return count

    def render_pages(
        self, page_numbers: list[int], max_workers: int = 4
    ) -> dict[int, str]:
        """
        Render the given page numbers in parallel chunks.
        Returns a mapping of page_number → image_path.
        Skips pages whose image already exists on disk (caching).
        """
        if not page_numbers:
            return {}

        self.ensure_output_dir()
        workers = min(max_workers, len(page_numbers))
        chunks = self._split_into_chunks(page_numbers, workers)

        logger.info(
            "Rendering %d pages with %d workers (pdf=%s, dpi=%d)",
            len(page_numbers), workers, os.path.basename(self._pdf_path), self._dpi,
        )

        all_results: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
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
                    logger.info("Rendered chunk of %d pages", len(chunk_results))
                except Exception as e:
                    logger.error("Chunk rendering failed: %s", e)

        return all_results

    @staticmethod
    def _split_into_chunks(items: list, num_chunks: int) -> list[list]:
        """Split a list into approximately equal chunks."""
        chunk_size = max(1, len(items) // num_chunks)
        return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
