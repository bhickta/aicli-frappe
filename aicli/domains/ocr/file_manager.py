"""
OCR File Manager — Physical file/directory operations for OCR jobs.
"""

import os
import shutil
import logging
from pathlib import Path

import frappe

from .constants import OCR_FILES_DIR, OCR_UPLOADS_DIR, IMAGES_SUBDIR

logger = logging.getLogger(__name__)


class FileManager:
    """Manages physical files and directories for OCR jobs."""

    @staticmethod
    def build_output_path(zip_path: str) -> str:
        """Derive the markdown output path from the ZIP path."""
        stem = Path(zip_path).stem
        # Use absolute path for reliability in background workers
        base_dir = os.path.abspath(frappe.get_site_path("public", "files", OCR_FILES_DIR))
        output_dir = os.path.join(base_dir, stem)
        os.makedirs(output_dir, exist_ok=True)
        return os.path.join(output_dir, f"{stem}.md")

    @staticmethod
    def get_images_dir(output_path: str) -> str:
        """Get the images directory path from the output path."""
        return os.path.abspath(os.path.join(os.path.dirname(output_path), IMAGES_SUBDIR))

    @staticmethod
    def get_uploads_dir() -> str:
        """Get the uploads directory path."""
        upload_dir = os.path.abspath(frappe.get_site_path("public", "files", OCR_FILES_DIR, OCR_UPLOADS_DIR))
        os.makedirs(upload_dir, exist_ok=True)
        return upload_dir

    @staticmethod
    def cleanup_job_files(output_path: str, is_completed: bool) -> None:
        """Delete physical assets for a job. Preserves images for completed jobs."""
        if not output_path:
            return

        abs_output_path = os.path.abspath(output_path)
        # Always delete the markdown file
        if os.path.exists(abs_output_path):
            os.remove(abs_output_path)
            logger.info("Deleted markdown: %s", abs_output_path)

        # Delete images only for incomplete jobs
        if not is_completed:
            images_dir = os.path.join(os.path.dirname(abs_output_path), IMAGES_SUBDIR)
            if os.path.exists(images_dir):
                shutil.rmtree(images_dir)
                logger.info("Deleted images directory: %s", images_dir)
        else:
            logger.info("Preserved images for completed job")

    @staticmethod
    def validate_zip(zip_path: str) -> str:
        """Validate and return the absolute ZIP path."""
        abs_path = os.path.abspath(zip_path)
        if not os.path.isfile(abs_path):
            # Try to see if it's relative to bench root
            bench_path = os.path.join(os.getcwd(), zip_path)
            if os.path.isfile(bench_path):
                return bench_path
            # Try to see if it's relative to sites
            sites_path = os.path.join(os.getcwd(), "sites", zip_path.lstrip("./"))
            if os.path.isfile(sites_path):
                return sites_path
                
            frappe.throw(f"ZIP file not found: {abs_path}")
        return abs_path

    @staticmethod
    def extract_zip(zip_path: str, images_dir: str) -> list[str]:
        """Extract a ZIP file and return a sorted list of image paths."""
        import zipfile
        
        os.makedirs(images_dir, exist_ok=True)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(images_dir)
        except Exception as e:
            frappe.throw(f"Failed to extract ZIP: {e}")
            
        allowed_exts = {".jpg", ".jpeg", ".png", ".webp"}
        extracted_images = []
        for root, _, files in os.walk(images_dir):
            for file in files:
                if any(file.lower().endswith(ext) for ext in allowed_exts):
                    extracted_images.append(os.path.join(root, file))
                    
        extracted_images.sort()
        return extracted_images
