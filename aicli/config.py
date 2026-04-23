"""Configuration structures for AI CLI."""

from pydantic_settings import BaseSettings, SettingsConfigDict

import os
import json
from pathlib import Path
from pydantic import BaseModel

CONFIG_DIR = Path.home() / ".config" / "aicli"
CONFIG_FILE = CONFIG_DIR / "settings.json"

PROVIDER_TYPE_CHOICES = ["ollama", "vllm", "lmstudio", "openai", "anthropic", "gemini"]


class AppConfig(BaseModel):
    """Configuration based on JSON settings."""

    # --- Provider Connection ---
    provider_type: str = "lmstudio"
    ollama_base_url: str = "http://localhost:11434"
    ollama_api_key: str = "ollama"
    vllm_base_url: str = "http://localhost:8000"
    vllm_api_key: str = "EMPTY"
    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_api_key: str = "lm_studio"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    model_name: str = "qwen3.5-9b"

    # --- LLM Tuning (UPSC Analyze Pipeline) ---
    analyze_max_tokens: int = 8192          # Token ceiling for classification, segmentation, aggregation
    analyze_temperature: float = 0.0        # Deterministic for exam evaluation
    segmenter_max_tokens: int = 500         # Smaller ceiling for segment extraction
    segmenter_max_retries: int = 2          # Retry attempts for segmentation LLM calls
    aggregation_chunk_size: int = 50        # Answers per aggregation LLM chunk
    analyze_step_models: dict[str, str] = {} # Step-specific default models (e.g., {"3": "gemma-4-e4b"})

    # --- LLM Tuning (Video Notes) ---
    notes_temperature: float = 0.2          # Slightly creative for note compression
    notes_max_tokens: int = 2048            # Token ceiling for note generation
    notes_chunk_size: int = 12000           # Characters per LLM chunk for notes

    # --- LLM Tuning (News Pipeline) ---
    news_batch_size: int = 10               # News lines per classification batch
    news_merge_temperature: float = 0.0     # Deterministic for news merging
    news_merge_max_tokens: int = 2048       # Token ceiling for news merge

    # --- Whisper Transcription ---
    whisper_batch_size: int = 24            # GPU batch size for Whisper inference
    whisper_beam_size: int = 1              # Beam search width (1 = greedy, fastest)

    # --- LLM Provider Defaults ---
    llm_default_temperature: float = 0.1    # Default temperature for generic LLM calls
    llm_default_max_tokens: int = 2000      # Default max tokens for generic LLM calls
    llm_default_max_retries: int = 3        # Default retry attempts for LLM calls
    llm_retry_backoff_base: int = 2         # Exponential backoff base (seconds)

    # --- Database ---
    db_connect_timeout: int = 30            # SQLite connection timeout (seconds)
    db_busy_timeout_ms: int = 5000

    # --- Frappe Integration ---
    frappe_url: str = "http://localhost:8000"
    frappe_api_key: str = "admin_key"
    frappe_api_secret: str = "admin_secret"
    use_frappe: bool = False

    # Image Rename Tuning
    image_rename_min_words: int = 3
    image_rename_max_words: int = 6          # SQLite busy_timeout pragma (milliseconds)

    def sync_from_frappe(self):
        """Fetch settings from Frappe UPSC Pipeline Settings DocType."""
        if not self.use_frappe:
            return
            
        import requests
        try:
            url = f"{self.frappe_url}/api/resource/UPSC%20Pipeline%20Settings/UPSC%20Pipeline%20Settings"
            headers = {
                "Authorization": f"token {self.frappe_api_key}:{self.frappe_api_secret}",
                "Host": "aicli.local"
            }
            res = requests.get(url, headers=headers, timeout=5)
            if res.ok:
                data = res.json().get("data", {})
                for key, value in data.items():
                    if hasattr(self, key):
                        # Special handling for JSON strings
                        if key == "analyze_step_models" and isinstance(value, str):
                            try:
                                setattr(self, key, json.loads(value))
                            except:
                                pass
                        else:
                            setattr(self, key, value)
        except Exception as e:
            print(f"Failed to sync from Frappe: {e}")

    def sync_to_frappe(self):
        """Save settings to Frappe UPSC Pipeline Settings DocType."""
        if not self.use_frappe:
            return

        import requests
        try:
            url = f"{self.frappe_url}/api/resource/UPSC%20Pipeline%20Settings/UPSC%20Pipeline%20Settings"
            headers = {
                "Authorization": f"token {self.frappe_api_key}:{self.frappe_api_secret}",
                "Host": "aicli.local",
                "Content-Type": "application/json"
            }
            data = self.model_dump()
            # Special handling for JSON fields
            if "analyze_step_models" in data:
                data["analyze_step_models"] = json.dumps(data["analyze_step_models"])
                
            res = requests.put(url, headers=headers, json=data, timeout=5)
            if not res.ok:
                print(f"Failed to sync to Frappe: {res.text}")
        except Exception as e:
            print(f"Failed to sync to Frappe: {e}")


def load_config() -> AppConfig:
    cfg = AppConfig()
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            cfg = AppConfig(**data)
        except Exception:
            pass
    
    # Sync from Frappe if enabled
    cfg.sync_from_frappe()
    return cfg


def save_config(cfg: AppConfig):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(cfg.model_dump_json(indent=2))
    # Sync to Frappe if enabled
    cfg.sync_to_frappe()


config = load_config()
