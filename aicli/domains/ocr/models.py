"""
OCR Domain Models — Typed data transfer objects for the OCR pipeline.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class OcrJobConfig:
    """Immutable configuration for an OCR job run."""
    zip_path: str
    model_name: str
    max_workers: int = 3


@dataclass
class OcrJobStatus:
    """Serializable snapshot of an OCR job's current state."""
    name: str
    zip_path: str
    output_path: str
    model_name: str
    status: str
    total_pages: int
    completed_pages: int
    failed_pages: int
    rendered_pages: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    pages: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to plain dict for JSON serialization."""
        return {
            "name": self.name,
            "zip_path": self.zip_path,
            "output_path": self.output_path,
            "model_name": self.model_name,
            "status": self.status,
            "total_pages": self.total_pages,
            "completed_pages": self.completed_pages,
            "failed_pages": self.failed_pages,
            "rendered_pages": self.rendered_pages,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "pages": self.pages,
        }


@dataclass
class PageResult:
    """Result of processing a single page through the LLM."""
    page_number: int
    markdown: str
    elapsed_seconds: float
