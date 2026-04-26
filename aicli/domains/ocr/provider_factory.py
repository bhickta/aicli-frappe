"""
OCR Provider Factory — Creates LLM providers from AICLI Settings.

Factory Pattern: centralizes provider construction to avoid duplication
across OCR service and analyze pipeline.
"""

import logging
from typing import Optional

import frappe

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Creates LLM provider instances from Frappe AICLI Settings."""

    def create(self, model_name: str):
        """Build and return a LangChain provider for the given model name."""
        doc = frappe.get_single("AICLI Settings")
        provider_type = doc.provider_type or "ollama"

        if provider_type in ("lms", "lmstudio"):
            return self._create_lms_provider(doc, model_name)
        return self._create_ollama_provider(doc, model_name)

    def get_lms_urls(self) -> tuple[Optional[str], Optional[str]]:
        """Return (api_root, base_url) for LM Studio, or (None, None) if not LMS."""
        doc = frappe.get_single("AICLI Settings")
        if doc.provider_type not in ("lms", "lmstudio"):
            return None, None
        base_url = (
            doc.get("lms_base_url") or doc.get("lm_studio_base_url") or "http://localhost:1234/v1"
        ).rstrip("/")
        api_root = base_url.replace("/v1", "")
        return api_root, base_url

    def _create_lms_provider(self, doc, model_name: str):
        from langchain_openai import ChatOpenAI
        from aicli.providers.base import LangChainProvider

        base_url = (
            doc.get("lms_base_url") or doc.get("lm_studio_base_url") or "http://localhost:1234/v1"
        )
        api_key = doc.get("lms_api_key") or doc.get("lm_studio_api_key") or "lms"
        llm = ChatOpenAI(base_url=base_url, api_key=api_key, model=model_name)
        logger.info("Created LMS provider for model %s at %s", model_name, base_url)
        return LangChainProvider(llm)

    def _create_ollama_provider(self, doc, model_name: str):
        from langchain_ollama import ChatOllama
        from aicli.providers.base import LangChainProvider

        base_url = doc.ollama_base_url or "http://localhost:11434"
        llm = ChatOllama(base_url=base_url, model=model_name)
        logger.info("Created Ollama provider for model %s at %s", model_name, base_url)
        return LangChainProvider(llm)
