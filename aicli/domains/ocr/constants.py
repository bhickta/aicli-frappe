"""
OCR Domain Constants — Single source of truth for prompts, defaults, and magic numbers.
"""

# ─── Default Configuration ────────────────────────────────────────
DEFAULT_DPI = 200
DEFAULT_MAX_WORKERS = 3
DEFAULT_MODEL = "gemma-4-27b-it"
MAX_LLM_RETRIES = 5
LLM_RETRY_BASE_DELAY = 2
LLM_RETRY_JITTER_RANGE = (0.5, 1.0)
LLM_MAX_TOKENS = 1500
LLM_TEMPERATURE = 0.0
LLM_IMAGE_MAX_SIZE = 1536
MODEL_LOAD_TIMEOUT = 120
MODEL_UNLOAD_TIMEOUT = 30
MODEL_CHECK_TIMEOUT = 10
ENQUEUE_TIMEOUT = 3600
ENQUEUE_QUEUE = "long"
CRASH_RECOVERY_DELAY = 5
CRASH_UNLOAD_DELAY = 2
PAGE_IMAGE_FORMAT = "page_{:04d}.ppm"
OCR_FILES_DIR = "aicli_ocr"
OCR_UPLOADS_DIR = "uploads"
IMAGES_SUBDIR = "images"

# ─── LM Studio API Paths ─────────────────────────────────────────
LMS_MODELS_ENDPOINT = "/models"
LMS_LOAD_ENDPOINT = "/api/v1/models/load"
LMS_UNLOAD_ENDPOINT = "/api/v1/models/unload"

# ─── LM Studio Load Config ───────────────────────────────────────
LMS_DEFAULT_CONTEXT_LENGTH = 32768
LMS_DEFAULT_EVAL_BATCH_SIZE = 512

# ─── Prompts ──────────────────────────────────────────────────────
SYSTEM_PROMPT = "You are a professional document digitizer. Output valid Markdown only."

PAGE_PROMPT_TEMPLATE = """You are a high-precision OCR engine.
Extract ALL text from this image (Page {page_number}/{total_pages}).

RULES:
1. Output ONLY the extracted text in Markdown. No preamble.
2. Preserve structure: # Headings, - Lists, | Tables |, **Bold**, *Italic*.
3. For images/photos, use placeholder: <<page_{page_number}_image_N>>
4. Maintain natural reading order.
5. Do NOT repeat these instructions in the output."""

# ─── Page Statuses ────────────────────────────────────────────────
STATUS_PENDING = "Pending"
STATUS_RENDERING = "Rendering"
STATUS_PROCESSING = "Processing"
STATUS_COMPLETED = "Completed"
STATUS_FAILED = "Failed"

# ─── Job Statuses ─────────────────────────────────────────────────
JOB_QUEUED = "Queued"
JOB_RUNNING = "Running"
JOB_COMPLETED = "Completed"
JOB_FAILED = "Failed"
JOB_PAUSED = "Paused"

# ─── Crash Keywords ───────────────────────────────────────────────
CRASH_KEYWORDS = ("model has crashed", "channel error")

# ─── Markdown Formatting ─────────────────────────────────────────
PAGE_MARKDOWN_HEADER = "<!-- Page {page_num} -->\n"
PAGE_MARKDOWN_SEPARATOR = "\n\n---\n\n"
