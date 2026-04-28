"""
Audio Repository — Frappe DB CRUD for Audio Job and Audio Track DocTypes.

Follows the same pattern as OcrRepository: thin persistence layer with no business logic.
"""

import json
import logging
from datetime import datetime

import frappe

from .constants import (
    JOB_QUEUED, JOB_RUNNING, JOB_COMPLETED, JOB_FAILED, JOB_PAUSED,
    TRACK_PENDING, TRACK_FAILED,
)

logger = logging.getLogger(__name__)


class AudioRepository:
    """Persistence layer for Audio Job / Audio Track DocTypes."""

    # ─── Job CRUD ─────────────────────────────────────────────────

    def create_job(
        self, whisper_model: str, llm_model: str, total_tracks: int
    ) -> str:
        """Create a new Audio Job record. Returns the job name (hash ID)."""
        doc = frappe.get_doc({
            "doctype": "Audio Job",
            "status": JOB_QUEUED,
            "whisper_model": whisper_model,
            "llm_model": llm_model,
            "total_tracks": total_tracks,
            "transcribed_tracks": 0,
            "analyzed_tracks": 0,
            "failed_tracks": 0,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name

    def get_job(self, job_name: str):
        """Return the Audio Job document."""
        return frappe.get_doc("Audio Job", job_name)

    def list_jobs(self) -> list[dict]:
        """List all Audio Jobs, newest first."""
        return frappe.get_all(
            "Audio Job",
            fields=["name", "status", "whisper_model", "llm_model",
                     "total_tracks", "transcribed_tracks", "analyzed_tracks",
                     "failed_tracks", "creation"],
            order_by="creation desc",
        )

    def mark_job_running(self, job_name: str) -> None:
        frappe.db.set_value("Audio Job", job_name, {
            "status": JOB_RUNNING,
            "started_at": datetime.now(),
        })
        frappe.db.commit()

    def mark_job_paused(self, job_name: str) -> None:
        frappe.db.set_value("Audio Job", job_name, "status", JOB_PAUSED)
        frappe.db.commit()

    def is_job_active(self, job_name: str) -> bool:
        """Return True if the job is still in Running state (not paused/stopped)."""
        status = frappe.db.get_value("Audio Job", job_name, "status")
        return status == JOB_RUNNING

    def finalize_job(self, job_name: str) -> str:
        """Determine final status and mark job complete or failed."""
        job = self.get_job(job_name)
        failed = frappe.db.count("Audio Track", {"audio_job": job_name, "status": TRACK_FAILED})
        total = job.total_tracks

        if failed == total:
            final_status = JOB_FAILED
        elif failed > 0:
            # Partial success — still mark completed but with failed count
            final_status = JOB_COMPLETED
        else:
            final_status = JOB_COMPLETED

        frappe.db.set_value("Audio Job", job_name, {
            "status": final_status,
            "failed_tracks": failed,
            "completed_at": datetime.now(),
        })
        frappe.db.commit()
        return final_status

    def update_job_counters(self, job_name: str) -> None:
        """Refresh the denormalized counters on the job from track statuses."""
        transcribed = frappe.db.count("Audio Track", {
            "audio_job": job_name,
            "status": ("in", ["Transcribed", "Analyzing", "Completed"]),
        })
        analyzed = frappe.db.count("Audio Track", {
            "audio_job": job_name,
            "status": "Completed",
        })
        failed = frappe.db.count("Audio Track", {
            "audio_job": job_name,
            "status": TRACK_FAILED,
        })
        frappe.db.set_value("Audio Job", job_name, {
            "transcribed_tracks": transcribed,
            "analyzed_tracks": analyzed,
            "failed_tracks": failed,
        })
        frappe.db.commit()

    def save_playlists(self, job_name: str, playlist_data: list[dict]) -> None:
        """Save the final playlist grouping JSON to the job."""
        frappe.db.set_value(
            "Audio Job", job_name, "playlist_json", json.dumps(playlist_data, ensure_ascii=False)
        )
        frappe.db.commit()

    def delete_job(self, job_name: str) -> None:
        """Delete a job and all its tracks."""
        # Delete tracks first
        tracks = frappe.get_all("Audio Track", filters={"audio_job": job_name}, pluck="name")
        for t in tracks:
            frappe.delete_doc("Audio Track", t, ignore_permissions=True, force=True)
        # Delete associated files
        try:
            attached = frappe.get_all("File", filters={
                "attached_to_doctype": "Audio Job",
                "attached_to_name": job_name,
            }, pluck="name")
            for f in attached:
                frappe.delete_doc("File", f, ignore_permissions=True, force=True)
        except Exception as e:
            logger.warning("File cleanup error for job %s: %s", job_name, e)
        # Delete the job
        frappe.delete_doc("Audio Job", job_name, ignore_permissions=True, force=True)
        frappe.db.commit()

    # ─── Track CRUD ───────────────────────────────────────────────

    def create_tracks(self, job_name: str, tracks_data: list[dict]) -> list[str]:
        """Bulk-create Audio Track records. Returns list of track names."""
        names = []
        for td in tracks_data:
            doc = frappe.get_doc({
                "doctype": "Audio Track",
                "audio_job": job_name,
                "file_url": td["file_url"],
                "original_filename": td["original_filename"],
                "status": TRACK_PENDING,
            }).insert(ignore_permissions=True)
            names.append(doc.name)
        frappe.db.commit()
        return names

    def get_pending_tracks(self, job_name: str, status: str = TRACK_PENDING) -> list[dict]:
        """Get all tracks in a given status for a job."""
        return frappe.get_all(
            "Audio Track",
            filters={"audio_job": job_name, "status": status},
            fields=["name", "file_url", "original_filename"],
            order_by="creation asc",
        )

    def get_transcribed_tracks(self, job_name: str) -> list[dict]:
        """Get all tracks that have been transcribed but not yet analyzed."""
        return frappe.get_all(
            "Audio Track",
            filters={"audio_job": job_name, "status": "Transcribed"},
            fields=["name", "file_url", "original_filename", "transcript", "duration_seconds"],
            order_by="creation asc",
        )

    def get_all_tracks(self, job_name: str) -> list[dict]:
        """Get all tracks for a job with full metadata."""
        return frappe.get_all(
            "Audio Track",
            filters={"audio_job": job_name},
            fields=[
                "name", "file_url", "original_filename", "status",
                "transcript", "duration_seconds", "genre", "mood",
                "language", "topics", "summary", "suggested_title",
                "content_type", "playlist_name", "analysis_json",
                "error", "elapsed_seconds",
            ],
            order_by="creation asc",
        )

    def get_completed_tracks_metadata(self, job_name: str) -> list[dict]:
        """Get completed tracks with analysis data for playlist grouping."""
        return frappe.get_all(
            "Audio Track",
            filters={"audio_job": job_name, "status": "Completed"},
            fields=[
                "name", "original_filename", "genre", "mood",
                "language", "topics", "summary", "suggested_title",
                "content_type", "duration_seconds",
            ],
            order_by="creation asc",
        )

    def set_track_status(self, track_name: str, status: str) -> None:
        frappe.db.set_value("Audio Track", track_name, "status", status)

    def save_transcript(
        self, track_name: str, transcript: str, duration: float, elapsed: float
    ) -> None:
        """Save transcription results to a track."""
        frappe.db.set_value("Audio Track", track_name, {
            "status": "Transcribed",
            "transcript": transcript,
            "duration_seconds": duration,
            "elapsed_seconds": elapsed,
        })
        frappe.db.commit()

    def save_analysis(self, track_name: str, analysis: dict) -> None:
        """Save AI analysis results to a track."""
        frappe.db.set_value("Audio Track", track_name, {
            "status": "Completed",
            "genre": analysis.get("genre", ""),
            "mood": analysis.get("mood", ""),
            "language": analysis.get("language", ""),
            "topics": json.dumps(analysis.get("topics", []), ensure_ascii=False),
            "summary": analysis.get("summary", ""),
            "suggested_title": analysis.get("suggested_title", ""),
            "content_type": analysis.get("content_type", ""),
            "analysis_json": json.dumps(analysis, ensure_ascii=False),
        })
        frappe.db.commit()

    def save_track_error(self, track_name: str, error: str) -> None:
        frappe.db.set_value("Audio Track", track_name, {
            "status": TRACK_FAILED,
            "error": error,
        })
        frappe.db.commit()

    def assign_playlist(self, track_name: str, playlist_name: str) -> None:
        """Assign a track to a playlist group."""
        frappe.db.set_value("Audio Track", track_name, "playlist_name", playlist_name)

    def bulk_assign_playlists(self, assignments: list[tuple[str, str]]) -> None:
        """Bulk assign playlist names. assignments = [(track_name, playlist_name), ...]"""
        for track_name, playlist_name in assignments:
            frappe.db.set_value("Audio Track", track_name, "playlist_name", playlist_name)
        frappe.db.commit()
