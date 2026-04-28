"""
Audio Job Service — Three-phase orchestrator: Transcribe → Analyze → Playlist.

Composes:
  - AudioRepository   (persistence)
  - AudioTranscriber   (Whisper STT)
  - AudioAnalyzer      (LLM analysis + playlist grouping)
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import frappe

from .constants import (
    TRACK_TRANSCRIBING, TRACK_TRANSCRIBED, TRACK_ANALYZING,
    TRACK_COMPLETED, TRACK_FAILED, JOB_COMPLETED,
)
from .repository import AudioRepository
from .transcriber import AudioTranscriber
from .analyzer import AudioAnalyzer

logger = logging.getLogger(__name__)


class AudioJobService:
    """Orchestrates the full audio pipeline: transcribe → analyze → playlist."""

    def __init__(self) -> None:
        self._repo = AudioRepository()

    # ─── Public API ───────────────────────────────────────────────

    def list_jobs(self) -> list[dict]:
        return self._repo.list_jobs()

    def create_job(
        self, file_urls: list[dict], whisper_model: str, llm_model: str
    ) -> str:
        """
        Create a new Audio Job with tracks.

        Args:
            file_urls: List of dicts with 'file_url' and 'original_filename'
            whisper_model: Whisper model size
            llm_model: LLM model name for analysis

        Returns:
            Job name (hash ID)
        """
        job_name = self._repo.create_job(whisper_model, llm_model, len(file_urls))
        self._repo.create_tracks(job_name, file_urls)
        logger.info("Created audio job %s with %d tracks", job_name, len(file_urls))
        return job_name

    def run_job(self, job_name: str, max_workers: int = 2) -> None:
        """Execute the full pipeline: transcribe → analyze → playlist."""
        job = self._repo.get_job(job_name)
        if job.status == JOB_COMPLETED:
            logger.info("Job %s already completed", job_name)
            return

        self._repo.mark_job_running(job_name)
        logger.info("Audio job %s started (workers=%d)", job_name, max_workers)

        try:
            # Phase 1: Transcription
            self._phase_transcribe(job_name, job.whisper_model, max_workers)

            if not self._repo.is_job_active(job_name):
                logger.info("Job %s paused after transcription", job_name)
                return

            # Phase 2: AI Analysis
            self._phase_analyze(job_name)

            if not self._repo.is_job_active(job_name):
                logger.info("Job %s paused after analysis", job_name)
                return

            # Phase 3: Playlist Grouping
            self._phase_playlist(job_name)

        except Exception as e:
            logger.error("Audio job %s failed: %s", job_name, e)
            frappe.db.set_value("Audio Job", job_name, "error", str(e)[:2000])
            frappe.db.commit()

        # Finalize
        final_status = self._repo.finalize_job(job_name)
        logger.info("Audio job %s finalized: %s", job_name, final_status)

    def get_status(self, job_name: str) -> dict:
        """Return a status snapshot for the frontend."""
        job = self._repo.get_job(job_name)
        return {
            "name": job.name,
            "status": job.status,
            "total_tracks": job.total_tracks,
            "transcribed_tracks": job.transcribed_tracks,
            "analyzed_tracks": job.analyzed_tracks,
            "failed_tracks": job.failed_tracks,
            "started_at": str(job.started_at) if job.started_at else None,
            "completed_at": str(job.completed_at) if job.completed_at else None,
            "error": job.error,
        }

    def get_tracks(self, job_name: str) -> list[dict]:
        """Return all tracks for a job."""
        tracks = self._repo.get_all_tracks(job_name)
        for t in tracks:
            # Parse topics JSON for frontend
            if t.get("topics"):
                try:
                    t["topics"] = json.loads(t["topics"])
                except (json.JSONDecodeError, TypeError):
                    t["topics"] = []
            else:
                t["topics"] = []
        return tracks

    def get_playlists(self, job_name: str) -> list[dict]:
        """Return the generated playlists for a job."""
        job = self._repo.get_job(job_name)
        if not job.playlist_json:
            return []
        try:
            playlists = json.loads(job.playlist_json)
            # Enrich each playlist with full track data
            tracks = self.get_tracks(job_name)
            for pl in playlists:
                pl["tracks"] = [
                    tracks[i] for i in pl.get("track_indices", [])
                    if 0 <= i < len(tracks)
                ]
            return playlists
        except (json.JSONDecodeError, TypeError):
            return []

    def delete_job(self, job_name: str) -> None:
        self._repo.delete_job(job_name)

    def stop_job(self, job_name: str) -> None:
        self._repo.mark_job_paused(job_name)

    # ─── Phase 1: Transcription ──────────────────────────────────

    def _phase_transcribe(
        self, job_name: str, whisper_model: str, max_workers: int
    ) -> None:
        """Transcribe all pending tracks using Whisper."""
        pending = self._repo.get_pending_tracks(job_name)
        if not pending:
            logger.info("No pending tracks for transcription in job %s", job_name)
            return

        logger.info("Phase 1: Transcribing %d tracks", len(pending))

        # Whisper model is shared (GPU resource), so we serialize transcription
        # but could parallelize in chunks if CPU-mode
        transcriber = AudioTranscriber(whisper_model)

        for track in pending:
            if not self._repo.is_job_active(job_name):
                break

            self._repo.set_track_status(track["name"], TRACK_TRANSCRIBING)

            try:
                # Resolve file URL to absolute path
                file_doc = frappe.get_doc("File", {"file_url": track["file_url"]})
                abs_path = file_doc.get_full_path()

                result = transcriber.transcribe(abs_path)

                self._repo.save_transcript(
                    track["name"],
                    result["text"],
                    result["duration"],
                    result["elapsed"],
                )
                logger.info(
                    "Transcribed: %s (%d chars, %.1fs)",
                    track["original_filename"], len(result["text"]), result["elapsed"],
                )

            except Exception as e:
                logger.error("Transcription failed for %s: %s", track["original_filename"], e)
                self._repo.save_track_error(track["name"], f"Transcription: {e}")

            self._repo.update_job_counters(job_name)

    # ─── Phase 2: AI Analysis ────────────────────────────────────

    def _phase_analyze(self, job_name: str) -> None:
        """Analyze transcribed tracks using LLM."""
        transcribed = self._repo.get_transcribed_tracks(job_name)
        if not transcribed:
            logger.info("No transcribed tracks to analyze in job %s", job_name)
            return

        logger.info("Phase 2: Analyzing %d tracks", len(transcribed))

        for track in transcribed:
            if not self._repo.is_job_active(job_name):
                break

            self._repo.set_track_status(track["name"], TRACK_ANALYZING)

            try:
                analysis = AudioAnalyzer.analyze_track(
                    transcript=track["transcript"],
                    filename=track["original_filename"],
                    duration=track["duration_seconds"] or 0,
                )
                self._repo.save_analysis(track["name"], analysis)
                logger.info(
                    "Analyzed: %s → %s / %s",
                    track["original_filename"],
                    analysis.get("genre", "?"),
                    analysis.get("content_type", "?"),
                )

            except Exception as e:
                logger.error("Analysis failed for %s: %s", track["original_filename"], e)
                self._repo.save_track_error(track["name"], f"Analysis: {e}")

            self._repo.update_job_counters(job_name)

    # ─── Phase 3: Playlist Grouping ──────────────────────────────

    def _phase_playlist(self, job_name: str) -> None:
        """Group completed tracks into playlists using LLM."""
        completed = self._repo.get_completed_tracks_metadata(job_name)
        if not completed:
            logger.info("No completed tracks for playlist grouping in job %s", job_name)
            return

        logger.info("Phase 3: Grouping %d tracks into playlists", len(completed))

        try:
            playlists = AudioAnalyzer.generate_playlists(completed)

            # Save playlist JSON to job
            self._repo.save_playlists(job_name, playlists)

            # Assign playlist names to individual tracks
            assignments = []
            for pl in playlists:
                for idx in pl.get("track_indices", []):
                    if 0 <= idx < len(completed):
                        assignments.append((completed[idx]["name"], pl["playlist_name"]))

            if assignments:
                self._repo.bulk_assign_playlists(assignments)

            logger.info(
                "Playlist grouping complete: %d playlists for %d tracks",
                len(playlists), len(completed),
            )

        except Exception as e:
            logger.error("Playlist generation failed for job %s: %s", job_name, e)
            # Non-fatal — tracks are still analyzed, just no playlists
            frappe.db.set_value(
                "Audio Job", job_name, "error",
                f"Playlist grouping failed: {e}"
            )
            frappe.db.commit()
