"""OCR Domain — LLM-powered PDF to Markdown conversion.

Public API:
  - OcrJobService: main orchestrator for creating, running, and managing OCR jobs
  - OcrRepository: database operations (for advanced use)
  - ProviderFactory: LLM provider creation (reusable by other domains)
"""

from .job_service import OcrJobService
from .repository import OcrRepository
from .provider_factory import ProviderFactory

__all__ = ["OcrJobService", "OcrRepository", "ProviderFactory"]
