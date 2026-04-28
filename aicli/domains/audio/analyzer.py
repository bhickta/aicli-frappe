"""
Audio Analyzer — LLM-powered track analysis and playlist generation.

Uses structured_invoke (Pydantic schemas) for reliable JSON output,
following the same proven pattern as VideoTaggerService.
"""

import json
import logging
from typing import List, Optional

from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate

from aicli.providers import get_provider
from .prompts import (
    TRACK_ANALYSIS_SYSTEM_PROMPT,
    TRACK_ANALYSIS_USER_PROMPT,
    PLAYLIST_SYSTEM_PROMPT,
    PLAYLIST_USER_PROMPT,
)
from .constants import (
    ANALYSIS_MAX_TOKENS,
    ANALYSIS_TEMPERATURE,
    PLAYLIST_MAX_TOKENS,
    PLAYLIST_TEMPERATURE,
)

logger = logging.getLogger(__name__)


# ─── Pydantic Schemas for Structured Output ──────────────────────

class TrackAnalysis(BaseModel):
    """Structured analysis of a single audio track."""
    genre: str = Field(description="Genre/category (e.g., Lecture, Podcast, Music, Audiobook, Interview)")
    mood: str = Field(description="Dominant mood/tone (e.g., Educational, Energetic, Calm, Humorous)")
    language: str = Field(description="Primary spoken language (e.g., English, Hindi)")
    topics: List[str] = Field(description="3-5 specific topics discussed")
    summary: str = Field(description="Concise 2-3 sentence summary of the content")
    suggested_title: str = Field(description="Clean descriptive title (max 60 chars)")
    content_type: str = Field(description="Broad category: lecture, podcast, music, audiobook, interview, conversation, monologue, narration, other")


class PlaylistEntry(BaseModel):
    """A single playlist group."""
    playlist_name: str = Field(description="Descriptive, engaging playlist name")
    description: str = Field(description="Short explanation of the grouping logic")
    track_indices: List[int] = Field(description="0-based indices of tracks in this playlist")


class PlaylistResult(BaseModel):
    """Full playlist grouping result."""
    playlists: List[PlaylistEntry] = Field(description="List of playlist groups, each track in exactly one")


# ─── Analyzer Service ────────────────────────────────────────────

class AudioAnalyzer:
    """Analyzes audio transcripts and generates playlist groupings via LLM."""

    @staticmethod
    def analyze_track(
        transcript: str,
        filename: str,
        duration: float,
        allow_reasoning: bool = False,
    ) -> dict:
        """
        Analyze a single track's transcript and return structured metadata.

        Returns dict with genre, mood, language, topics, summary, suggested_title, content_type.
        """
        provider = get_provider()

        # Truncate transcript to avoid context overflow
        truncated = transcript[:4000] if len(transcript) > 4000 else transcript

        prompt_template = PromptTemplate.from_template(TRACK_ANALYSIS_USER_PROMPT)
        rendered_prompt = prompt_template.format(
            filename=filename,
            duration=f"{duration:.0f}",
            transcript=truncated,
        )

        try:
            result = provider.structured_invoke(
                schema=TrackAnalysis,
                prompt=rendered_prompt,
                system_prompt=TRACK_ANALYSIS_SYSTEM_PROMPT,
                allow_reasoning=allow_reasoning,
            )
            return result.model_dump()
        except Exception as e:
            logger.error("Track analysis failed for %s: %s", filename, e)
            # Fallback: try with complete_text_json
            try:
                result = provider.complete_text_json(
                    prompt=rendered_prompt,
                    system_prompt=TRACK_ANALYSIS_SYSTEM_PROMPT,
                    temperature=ANALYSIS_TEMPERATURE,
                    max_tokens=ANALYSIS_MAX_TOKENS,
                )
                return result
            except Exception as e2:
                raise ValueError(f"Track analysis failed: {e2}") from e

    @staticmethod
    def generate_playlists(
        tracks_metadata: list[dict],
        allow_reasoning: bool = True,
    ) -> list[dict]:
        """
        Given a list of analyzed tracks, group them into playlists.

        Args:
            tracks_metadata: List of dicts with keys: original_filename, genre, mood,
                           topics, summary, content_type, duration_seconds, suggested_title

        Returns:
            List of playlist dicts with: playlist_name, description, track_indices
        """
        if not tracks_metadata:
            return []

        if len(tracks_metadata) == 1:
            # Single track — just create one playlist
            return [{
                "playlist_name": tracks_metadata[0].get("suggested_title", "My Playlist"),
                "description": "Single track playlist",
                "track_indices": [0],
            }]

        # Build the track listing string
        lines = []
        for i, t in enumerate(tracks_metadata):
            topics_str = t.get("topics", "[]")
            if isinstance(topics_str, str):
                try:
                    topics_list = json.loads(topics_str)
                except (json.JSONDecodeError, TypeError):
                    topics_list = [topics_str]
            else:
                topics_list = topics_str

            dur = t.get("duration_seconds", 0)
            dur_min = f"{dur / 60:.1f}min" if dur else "??min"

            lines.append(
                f"[{i}] \"{t.get('suggested_title', t.get('original_filename', 'Unknown'))}\" "
                f"| Genre: {t.get('genre', '?')} | Mood: {t.get('mood', '?')} "
                f"| Type: {t.get('content_type', '?')} | Duration: {dur_min} "
                f"| Topics: {', '.join(topics_list[:3])}"
            )

        track_listing = "\n".join(lines)

        prompt_template = PromptTemplate.from_template(PLAYLIST_USER_PROMPT)
        rendered_prompt = prompt_template.format(
            count=len(tracks_metadata),
            track_listing=track_listing,
        )

        provider = get_provider()

        try:
            result = provider.structured_invoke(
                schema=PlaylistResult,
                prompt=rendered_prompt,
                system_prompt=PLAYLIST_SYSTEM_PROMPT,
                allow_reasoning=allow_reasoning,
            )
            playlists = [p.model_dump() for p in result.playlists]
        except Exception as e:
            logger.error("Playlist generation via structured_invoke failed: %s", e)
            # Fallback
            try:
                result = provider.complete_text_json(
                    prompt=rendered_prompt,
                    system_prompt=PLAYLIST_SYSTEM_PROMPT,
                    temperature=PLAYLIST_TEMPERATURE,
                    max_tokens=PLAYLIST_MAX_TOKENS,
                )
                playlists = result.get("playlists", [result])
            except Exception as e2:
                logger.error("Playlist fallback also failed: %s", e2)
                # Ultimate fallback: one playlist with all tracks
                playlists = [{
                    "playlist_name": "All Tracks",
                    "description": "Auto-grouped (AI grouping unavailable)",
                    "track_indices": list(range(len(tracks_metadata))),
                }]

        # Validate: ensure every track is assigned
        assigned = set()
        for p in playlists:
            for idx in p.get("track_indices", []):
                if 0 <= idx < len(tracks_metadata):
                    assigned.add(idx)

        # Add unassigned tracks to a catchall
        unassigned = [i for i in range(len(tracks_metadata)) if i not in assigned]
        if unassigned:
            playlists.append({
                "playlist_name": "Uncategorized",
                "description": "Tracks that could not be grouped",
                "track_indices": unassigned,
            })

        return playlists
