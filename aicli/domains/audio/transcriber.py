"""
Audio Transcriber — Whisper integration for MP3/audio files.

Reuses the faster-whisper pattern from services/video/transcriber.py
but tailored for full-file audio transcription (not sparse video clips).
"""

import time
import logging
import subprocess
import json
from pathlib import Path
from typing import Optional

from .constants import WHISPER_BATCH_SIZE, WHISPER_BEAM_SIZE

logger = logging.getLogger(__name__)


class AudioTranscriber:
    """Manages speech-to-text for audio files using faster-whisper."""

    def __init__(self, whisper_model_size: str = "base") -> None:
        self._model_size = whisper_model_size
        self._model = None

    def _ensure_model(self):
        """Lazy-load the Whisper model on first use."""
        if self._model is not None:
            return

        try:
            from faster_whisper import WhisperModel, BatchedInferencePipeline
        except ImportError:
            raise ImportError(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            )

        logger.info("Loading Whisper model: %s", self._model_size)
        try:
            # Try GPU first
            model = WhisperModel(
                self._model_size, device="cuda", compute_type="float16"
            )
        except Exception:
            logger.warning("CUDA not available, falling back to CPU for Whisper")
            model = WhisperModel(
                self._model_size, device="cpu", compute_type="int8"
            )

        self._model = BatchedInferencePipeline(model=model)
        logger.info("Whisper model loaded: %s", self._model_size)

    def transcribe(self, audio_path: str) -> dict:
        """
        Transcribe an audio file to text.

        Args:
            audio_path: Absolute path to the audio file (MP3, WAV, etc.)

        Returns:
            dict with keys: text (str), duration (float), segments (list)
        """
        self._ensure_model()

        start_t = time.perf_counter()
        logger.info("Transcribing: %s", Path(audio_path).name)

        # Get duration via ffprobe
        duration = self._get_duration(audio_path)

        # faster-whisper handles MP3 natively via its internal ffmpeg
        segments, info = self._model.transcribe(
            audio_path,
            batch_size=WHISPER_BATCH_SIZE,
            beam_size=WHISPER_BEAM_SIZE,
            language=None,  # Auto-detect
            vad_filter=True,
        )

        seg_list = list(segments)
        full_text = " ".join(s.text.strip() for s in seg_list).strip()

        elapsed = time.perf_counter() - start_t
        detected_lang = info.language if hasattr(info, "language") else "unknown"

        logger.info(
            "Transcribed %s: %d chars, %.1fs, lang=%s",
            Path(audio_path).name, len(full_text), elapsed, detected_lang,
        )

        return {
            "text": full_text,
            "duration": duration or (info.duration if hasattr(info, "duration") else 0),
            "language": detected_lang,
            "elapsed": elapsed,
            "segment_count": len(seg_list),
        }

    @staticmethod
    def _get_duration(audio_path: str) -> Optional[float]:
        """Get audio duration in seconds via ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", audio_path,
            ]
            out = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(out.stdout)
            return float(data["format"].get("duration", 0))
        except Exception:
            return None
