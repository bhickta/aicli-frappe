"""
OCR Markdown Writer — File I/O for markdown output.
"""

import os
import logging

from .constants import PAGE_MARKDOWN_HEADER, PAGE_MARKDOWN_SEPARATOR

logger = logging.getLogger(__name__)


class MarkdownWriter:
    """Handles all markdown file I/O operations for OCR output."""

    def __init__(self, output_path: str) -> None:
        self._output_path = output_path

    @property
    def path(self) -> str:
        return self._output_path

    def ensure_dir(self) -> None:
        os.makedirs(os.path.dirname(self._output_path), exist_ok=True)

    def append_page(self, page_num: int, markdown: str) -> None:
        """Append a single page's markdown to the output file."""
        self.ensure_dir()
        with open(self._output_path, "a", encoding="utf-8") as f:
            f.write(PAGE_MARKDOWN_HEADER.format(page_num=page_num))
            f.write(markdown)
            f.write(PAGE_MARKDOWN_SEPARATOR)

    def write(self, content: str) -> None:
        """Write the entire markdown content, overwriting existing file."""
        self.ensure_dir()
        with open(self._output_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Wrote full markdown content to %s", self._output_path)

    def write_full(self, pages: list[dict]) -> None:
        """Write all completed pages from records as a single markdown file."""
        content = self.assemble_from_pages(pages)
        self.write(content)


    def read(self) -> str:
        """Read the markdown file content. Returns empty string if not found."""
        if os.path.isfile(self._output_path):
            with open(self._output_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def delete(self) -> None:
        """Delete the markdown file if it exists."""
        if os.path.exists(self._output_path):
            os.remove(self._output_path)
            logger.info("Deleted markdown file: %s", self._output_path)

    @staticmethod
    def assemble_from_pages(pages: list[dict]) -> str:
        """Assemble markdown string from page records without writing to disk."""
        parts = []
        for p in pages:
            parts.append(PAGE_MARKDOWN_HEADER.format(page_num=p["page_number"]))
            parts.append(p.get("markdown_output") or "")
            parts.append(PAGE_MARKDOWN_SEPARATOR)
        return "".join(parts)
