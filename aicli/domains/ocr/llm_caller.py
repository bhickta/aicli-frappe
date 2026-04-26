"""
OCR LLM Caller — Atomic retry logic for vision-LLM page extraction.
"""

import time
import random
import logging
from typing import Optional

from .constants import (
    SYSTEM_PROMPT, PAGE_PROMPT_TEMPLATE,
    MAX_LLM_RETRIES, LLM_RETRY_BASE_DELAY, LLM_RETRY_JITTER_RANGE,
    LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_IMAGE_MAX_SIZE,
    CRASH_KEYWORDS, CRASH_RECOVERY_DELAY, CRASH_UNLOAD_DELAY,
)
from .models import PageResult

logger = logging.getLogger(__name__)


class LlmCaller:
    """Calls a vision LLM to extract markdown from a page image with atomic retry."""

    def __init__(self, provider, total_pages: int, model_manager=None, model_name: Optional[str] = None):
        self._provider = provider
        self._total_pages = total_pages
        self._model_manager = model_manager
        self._model_name = model_name

    def process_page(self, image_path: str, page_number: int) -> PageResult:
        """Extract markdown from a page image. Retries with exponential backoff."""
        prompt = PAGE_PROMPT_TEMPLATE.format(page_number=page_number, total_pages=self._total_pages)
        start_time = time.perf_counter()

        for attempt in range(MAX_LLM_RETRIES):
            try:
                markdown = self._provider.describe_image(
                    image_path=image_path, prompt=prompt, system_prompt=SYSTEM_PROMPT,
                    max_size=LLM_IMAGE_MAX_SIZE, temperature=LLM_TEMPERATURE,
                    max_tokens=LLM_MAX_TOKENS, max_retries=1,
                )
                elapsed = time.perf_counter() - start_time
                logger.info("Page %d/%d done in %.1fs (attempt %d)", page_number, self._total_pages, elapsed, attempt + 1)
                return PageResult(page_number=page_number, markdown=markdown, elapsed_seconds=elapsed)
            except Exception as e:
                self._handle_retry(e, attempt, page_number)

        raise RuntimeError(f"All {MAX_LLM_RETRIES} retries exhausted for page {page_number}")

    def _handle_retry(self, error: Exception, attempt: int, page_number: int) -> None:
        is_last = attempt >= MAX_LLM_RETRIES - 1
        error_str = self._extract_error_string(error)
        if is_last:
            logger.error("Page %d failed after %d attempts: %s", page_number, MAX_LLM_RETRIES, error_str)
            raise Exception(error_str)

        if self._is_model_crash(error_str):
            logger.warning("Model crash on page %d (attempt %d), recovering...", page_number, attempt + 1)
            self._recover_model()
        else:
            delay = (LLM_RETRY_BASE_DELAY ** attempt) + random.uniform(*LLM_RETRY_JITTER_RANGE)
            logger.warning("Page %d attempt %d failed, retrying in %.1fs", page_number, attempt + 1, delay)
            time.sleep(delay)

    def _recover_model(self) -> None:
        if not self._model_manager or not self._model_name:
            return
        self._model_manager.unload_model(self._model_name)
        time.sleep(CRASH_UNLOAD_DELAY)
        self._model_manager.load_model(self._model_name)
        time.sleep(CRASH_RECOVERY_DELAY)

    @staticmethod
    def _is_model_crash(error_str: str) -> bool:
        return any(kw in error_str.lower() for kw in CRASH_KEYWORDS)

    @staticmethod
    def _extract_error_string(error: Exception) -> str:
        parts = [str(error)]
        if hasattr(error, "response") and hasattr(error.response, "text"):
            parts.append(error.response.text)
        return " | ".join(parts)
