"""
OCR Model Manager — LM Studio model load/unload/check operations.
"""

import logging
import requests
from typing import Optional

from .constants import (
    LMS_MODELS_ENDPOINT, LMS_LOAD_ENDPOINT, LMS_UNLOAD_ENDPOINT,
    LMS_DEFAULT_CONTEXT_LENGTH, LMS_DEFAULT_EVAL_BATCH_SIZE,
    MODEL_LOAD_TIMEOUT, MODEL_UNLOAD_TIMEOUT, MODEL_CHECK_TIMEOUT,
)

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages LM Studio model lifecycle: check, load, unload."""

    def __init__(self, api_root: str, base_url: str) -> None:
        self._api_root = api_root
        self._base_url = base_url

    def ensure_loaded(self, model_name: str) -> None:
        """Load the model only if it isn't already loaded. Preserves user settings."""
        if self._is_loaded(model_name):
            logger.info("Model %s already loaded, preserving settings", model_name)
            return
        self.load_model(model_name)

    def load_model(self, model_name: str) -> None:
        """Load a model via the LM Studio REST API. Raises on failure."""
        url = f"{self._api_root}{LMS_LOAD_ENDPOINT}"
        payload = {
            "model": model_name,
            "context_length": LMS_DEFAULT_CONTEXT_LENGTH,
            "flash_attention": True,
            "offload_kv_cache_to_gpu": False,
            "eval_batch_size": LMS_DEFAULT_EVAL_BATCH_SIZE,
            "echo_load_config": True,
        }
        logger.info("Loading model %s via %s", model_name, url)
        try:
            res = requests.post(url, json=payload, timeout=MODEL_LOAD_TIMEOUT)
            if res.ok:
                logger.info("Model loaded: %s", res.json())
            else:
                error_msg = f"LM Studio load failed ({res.status_code}): {res.text}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
        except requests.exceptions.Timeout:
            error_msg = f"LM Studio timed out after {MODEL_LOAD_TIMEOUT}s while loading {model_name}. Is the model too large or disk too slow?"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"LM Studio load request failed: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def unload_model(self, model_name: str) -> None:
        """Unload a model via the LM Studio REST API."""
        url = f"{self._api_root}{LMS_UNLOAD_ENDPOINT}"
        payload = {"instance_id": model_name}
        logger.info("Unloading model %s", model_name)
        try:
            res = requests.post(url, json=payload, timeout=MODEL_UNLOAD_TIMEOUT)
            if res.ok:
                logger.info("Model unloaded: %s", res.json())
            else:
                logger.warning("Unload response: %s %s", res.status_code, res.text)
        except Exception as e:
            logger.error("Unload request failed: %s", e)

    def _is_loaded(self, model_name: str) -> bool:
        """Check if a model is currently loaded."""
        try:
            res = requests.get(
                f"{self._base_url}{LMS_MODELS_ENDPOINT}",
                timeout=MODEL_CHECK_TIMEOUT,
            )
            if res.ok:
                loaded_ids = [m["id"] for m in res.json().get("data", [])]
                return model_name in loaded_ids
        except Exception as e:
            logger.warning("Could not check loaded models: %s", e)
        return False
