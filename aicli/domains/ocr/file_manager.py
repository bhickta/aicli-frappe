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
    def _get_path(*parts) -> str:
        """Internal helper to get a reliable absolute path within the site directory."""
        # frappe.get_site_path() might return path starting with ./aicli.local
        # We ensure it's absolute relative to the bench root.
        site_path = frappe.get_site_path()
        if site_path.startswith("./"):
            # Convert ./site-name to sites/site-name
            site_path = os.path.join("sites", site_path[2:])
        
        # Join with bench root if not absolute
        if not os.path.isabs(site_path):
            site_path = os.path.join(frappe.utils.get_bench_path(), site_path)
            
        return os.path.abspath(os.path.join(site_path, *parts))

    @staticmethod
    def build_output_path(zip_path: str) -> str:
        """Derive the markdown output path from the ZIP path."""
        stem = Path(zip_path).stem
        output_dir = FileManager._get_path("public", "files", OCR_FILES_DIR, stem)
        os.makedirs(output_dir, exist_ok=True)
        return os.path.join(output_dir, f"{stem}.md")

    @staticmethod
    def get_images_dir(output_path: str) -> str:
        """Get the images directory path from the output path."""
        return os.path.join(os.path.dirname(output_path), IMAGES_SUBDIR)

    @staticmethod
    def get_uploads_dir() -> str:
        """Get the uploads directory path."""
        upload_dir = FileManager._get_path("public", "files", OCR_FILES_DIR, OCR_UPLOADS_DIR)
        os.makedirs(upload_dir, exist_ok=True)
        return upload_dir

    @staticmethod
    def cleanup_job_files(output_path: str, is_completed: bool) -> None:
        """Delete physical assets for a job. Preserves images for completed jobs."""
        if not output_path:
            return

        # Always delete the markdown file
        if os.path.exists(output_path):
            os.remove(output_path)
            logger.info("Deleted markdown: %s", output_path)

        # Delete images only for incomplete jobs
        if not is_completed:
            images_dir = os.path.join(os.path.dirname(output_path), IMAGES_SUBDIR)
            if os.path.exists(images_dir):
                shutil.rmtree(images_dir)
                logger.info("Deleted images directory: %s", images_dir)
        else:
            logger.info("Preserved images for completed job")

    @staticmethod
    def validate_zip(zip_path: str) -> str:
        """Validate and return the absolute ZIP path."""
        if os.path.isfile(zip_path):
            return os.path.abspath(zip_path)
            
        # Try relative to bench root
        bench_relative = os.path.join(frappe.utils.get_bench_path(), zip_path)
        if os.path.isfile(bench_relative):
            return bench_relative
            
        # Try fixing the ./site-name -> sites/site-name issue
        if zip_path.startswith("./"):
            fixed_path = os.path.join(frappe.utils.get_bench_path(), "sites", zip_path[2:])
            if os.path.isfile(fixed_path):
                return fixed_path
                
        frappe.throw(f"ZIP file not found: {zip_path}")
        return zip_path

    @staticmethod
    def get_full_path_from_url(file_url: str) -> str:
        """Resolve a Frappe File URL to a full local filesystem path.
        
        Uses Frappe's native File.get_full_path() for reliable resolution
        across web server and background worker contexts.
        """
        # Use Frappe's own File document to resolve the path
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        return file_doc.get_full_path()

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
