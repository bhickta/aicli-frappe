"""
Audio Domain Constants — Single source of truth for statuses, defaults, and config.
"""

# ─── Track Statuses ───────────────────────────────────────────────
TRACK_PENDING = "Pending"
TRACK_TRANSCRIBING = "Transcribing"
TRACK_TRANSCRIBED = "Transcribed"
TRACK_ANALYZING = "Analyzing"
TRACK_COMPLETED = "Completed"
TRACK_FAILED = "Failed"

# ─── Job Statuses ─────────────────────────────────────────────────
JOB_QUEUED = "Queued"
JOB_RUNNING = "Running"
JOB_COMPLETED = "Completed"
JOB_FAILED = "Failed"
JOB_PAUSED = "Paused"

# ─── Defaults ─────────────────────────────────────────────────────
DEFAULT_WHISPER_MODEL = "base"
DEFAULT_LLM_MODEL = "gemma-4-27b-it"
DEFAULT_MAX_WORKERS = 2
ENQUEUE_TIMEOUT = 7200  # 2 hours for large audio libraries
ENQUEUE_QUEUE = "default"

# ─── Whisper Config ───────────────────────────────────────────────
WHISPER_BATCH_SIZE = 16
WHISPER_BEAM_SIZE = 1  # Greedy = fastest

# ─── LLM Config ──────────────────────────────────────────────────
ANALYSIS_MAX_TOKENS = 2048
ANALYSIS_TEMPERATURE = 0.1
PLAYLIST_MAX_TOKENS = 4096
PLAYLIST_TEMPERATURE = 0.2

# ─── Supported Audio Extensions ──────────────────────────────────
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma", ".opus"}
