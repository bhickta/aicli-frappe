"""Step 1: Convert PDF pages to PNG images.

Uses PyMuPDF (fitz) to render each page at configurable DPI, avoiding large RAM/swap usage.
Already-converted pages are skipped for resumability.

Memory safety:
  - Explicit pixmap disposal after each page (``del pix``)
  - Periodic ``gc.collect()`` to reclaim any lingering C-level buffers
"""
import gc
from pathlib import Path

import fitz

from aicli.domains.analyze.database import AnalyzeDB

# Force GC every N pages to release PyMuPDF's native allocations
_GC_EVERY_N_PAGES = 5


class PDFConverterService:
    """Convert PDF pages to PNG images at specified DPI."""

    def convert(self, pdf_path: Path, output_dir: Path, db: AnalyzeDB, dpi: int = 200) -> int:
        """Convert all pages of a PDF to PNG images.

        Args:
            pdf_path: Path to the PDF file.
            output_dir: Directory to store page images.
            db: Database instance.
            dpi: Resolution for rendering. 200 is good for handwriting.

        Returns:
            Count of NEW pages converted (0 if already done).
        """
        pdf_name = pdf_path.name
        existing = db.get_pages_for_pdf(pdf_name)
        if existing:
            return 0  # Already converted

        # Create per-PDF image directory
        pdf_image_dir = output_dir / pdf_path.stem
        pdf_image_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(pdf_path))
        # PyMuPDF's default DPI is 72. zoom = dpi / 72.
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        count = 0
        try:
            for i, page in enumerate(doc, start=1):
                image_path = pdf_image_dir / f"page_{i:04d}.png"
                pix = page.get_pixmap(matrix=mat, alpha=False)
                pix.save(str(image_path))
                # Release native pixel buffer immediately to avoid accumulation
                del pix
                db.insert_page(pdf_name, i, str(image_path))
                count += 1

                if count % _GC_EVERY_N_PAGES == 0:
                    gc.collect()
        finally:
            doc.close()

        db.log_processing(pdf_name, "pdf_to_images", "done")
        return count

    def convert_all(
        self, data_dir: Path, output_dir: Path, db: AnalyzeDB, dpi: int = 200
    ) -> tuple[int, int]:
        """Convert all PDFs in a directory.

        Returns:
            (pdf_count, total_new_pages)
        """
        pdf_files = sorted(data_dir.glob("*.pdf"))
        total_pages = 0
        pdf_count = 0

        for pdf_path in pdf_files:
            new_pages = self.convert(pdf_path, output_dir, db, dpi)
            if new_pages > 0:
                pdf_count += 1
                total_pages += new_pages

        return pdf_count, total_pages
