"""Batch Speech-to-Text tools — async transcription of long or multiple audio files.

Flow: create job → start → poll until terminal → get files → download transcripts.

Endpoints
---------
POST   /stt/v3/batch/jobs                         create
POST   /stt/v3/batch/jobs/{job_id}/start          start
GET    /stt/v3/batch/jobs/{job_id}                status
GET    /stt/v3/batch/jobs/{job_id}/files          per-file results + transcript_url
POST   /stt/v3/batch/jobs/{job_id}/cancel         cancel
GET    /stt/v3/batch/jobs                         list jobs
GET    <presigned transcript_url>                 download transcript (no auth)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastmcp import Context, FastMCP
from pydantic import Field

from gnani_mcp.tools._common import SttLanguageCode, guess_audio_mime, ready_ctx, resolve_file_input

logger = logging.getLogger("gnani_mcp.tools.stt_batch")

_BASE = "/stt/v3/batch/jobs"

# Polling config — poll every 10 s, give up after 30 min.
_POLL_INTERVAL_SECONDS = 10
_MAX_POLL_ATTEMPTS = 180  # 30 min

# Job statuses that mean we should stop polling.
_TERMINAL_STATUSES = frozenset(
    {"COMPLETED", "PARTIAL_FAILURE", "FAILED", "START_FAILED", "CANCELLED"}
)

# Batch STT language codes (Gujarati and Punjabi NOT supported here).
BatchLanguageCode = str  # up to 3 comma-separated BCP-47 codes, e.g. "hi-IN,en-IN"


def register(mcp: FastMCP) -> None:
    """Register all Batch STT tools onto *mcp*."""

    @mcp.tool(
        name="gnani_stt_batch_transcribe",
        description=(
            "Transcribe long audio files (up to 4 hours each) or multiple files "
            "asynchronously using the Gnani Prisma v2.5 Batch STT API.\n\n"
            "**This tool runs the full flow automatically:** "
            "create job → start → poll every 10 s → fetch transcripts → return results.\n\n"
            "**Two ways to provide audio:**\n"
            "• Local file — set ``audio_path`` (max 10 MB per file via direct upload)\n"
            "• Public URL — set ``audio_url`` (HTTPS link, no size cap, bounded by 4-hour limit)\n\n"
            "**Supported languages (8):** bn-IN, en-IN, hi-IN, kn-IN, ml-IN, mr-IN, ta-IN, te-IN.\n"
            "Gujarati (gu-IN) and Punjabi (pa-IN) are NOT supported in Batch — use "
            "``gnani_stt_transcribe`` (REST) for those.\n\n"
            "**Diarization:** set ``with_diarization=True`` + ``num_speakers=2`` to get "
            "per-speaker segments in the transcript.\n\n"
            "**Denoising:** set ``with_denoise=True`` for noisy call-centre or field recordings. "
            "Leave off for clean audio — it adds processing time without changing the transcript.\n\n"
            "**Multi-language identification:** pass up to 3 comma-separated codes as "
            "``language_code`` (e.g. ``'hi-IN,en-IN'``) and the API identifies the language "
            "per file automatically."
        ),
    )
    async def gnani_stt_batch_transcribe(
        ctx: Context,
        language_code: str = Field(
            description=(
                "BCP-47 language code. Supported: bn-IN, en-IN, hi-IN, kn-IN, ml-IN, "
                "mr-IN, ta-IN, te-IN. Pass up to 3 comma-separated codes for automatic "
                "language identification per file (e.g. 'hi-IN,en-IN')."
            ),
        ),
        audio_path: str | None = Field(
            default=None,
            description=(
                "Local path to the audio file (max 10 MB). "
                "Supported formats: wav, mp3, mp4, flac, ogg, opus, m4a, aac, webm, amr."
            ),
        ),
        audio_url: str | None = Field(
            default=None,
            description=(
                "Public HTTPS URL to the audio file (S3 presigned URLs work). "
                "No 10 MB cap — bounded only by the 4-hour duration limit."
            ),
        ),
        with_diarization: bool = Field(
            default=False,
            description="Enable speaker diarization (who said what). Requires num_speakers.",
        ),
        num_speakers: int | None = Field(
            default=None,
            description="Number of speakers (max 2). Required when with_diarization=True.",
        ),
        with_denoise: bool = Field(
            default=False,
            description=(
                "Denoise the audio before transcription. "
                "Use for noisy recordings; leave off for clean audio."
            ),
        ),
        is_multi_channel: bool = Field(
            default=False,
            description="Set True only for true multi-channel audio files.",
        ),
        callback_url: str | None = Field(
            default=None,
            description=(
                "Optional HTTPS webhook URL. Gnani will POST results here when the job "
                "reaches a terminal state — useful for long jobs you don't want to poll."
            ),
        ),
    ) -> dict[str, Any]:
        sc = await ready_ctx(ctx)

        if audio_path is None and audio_url is None:
            raise ValueError("Provide either audio_path (local file) or audio_url (public HTTPS URL).")
        if audio_path is not None and audio_url is not None:
            raise ValueError("Provide only one of audio_path or audio_url, not both.")

        config: dict[str, Any] = {
            "model": "gnani-prisma-v2.5",
            "language_code": language_code,
            "mode": "transcribe",
            "with_diarization": with_diarization,
            "is_multi_channel": is_multi_channel,
            "with_denoise": with_denoise,
        }
        if with_diarization and num_speakers is not None:
            config["num_speakers"] = num_speakers

        # ── Step 1: Create job ──────────────────────────────────────────
        await ctx.info("Creating batch STT job…")

        if audio_path is not None:
            # Multipart upload
            async with resolve_file_input(file_path=audio_path) as path:
                with path.open("rb") as fh:
                    create_payload = await sc.client.post_multipart(
                        _BASE,
                        data={"config": json.dumps(config), **({"callback_url": callback_url} if callback_url else {})},
                        files={"files": (path.name, fh, guess_audio_mime(path))},
                    )
        else:
            # Public URL (JSON body)
            body: dict[str, Any] = {
                "config": config,
                "source": {
                    "type": "cloud_storage",
                    "auth": {"mode": "public"},
                    "paths": [audio_url],
                },
            }
            if callback_url:
                body["callback_url"] = callback_url
            create_payload = await sc.client.post_json(_BASE, json_body=body)

        job_id: str = create_payload["job_id"]
        await ctx.info(f"Job created: {job_id} — starting transcription…")

        # ── Step 2: Start job ───────────────────────────────────────────
        await sc.client.post_json(f"{_BASE}/{job_id}/start", json_body={})
        await ctx.info("Job started — polling for completion (every 10 s)…")

        # ── Step 3: Poll until terminal ─────────────────────────────────
        status_payload: dict[str, Any] = {}
        for attempt in range(_MAX_POLL_ATTEMPTS):
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            status_payload = await sc.client.get_json(f"{_BASE}/{job_id}")
            status = status_payload.get("status", "")
            progress = status_payload.get("progress", {})

            await ctx.report_progress(attempt + 1, _MAX_POLL_ATTEMPTS)

            if (attempt + 1) % 3 == 0:  # log every 30 s
                await ctx.info(
                    f"[{job_id}] {status} — "
                    f"{progress.get('completed_files', 0)}/{progress.get('total_files', '?')} files"
                )

            if status in _TERMINAL_STATUSES:
                break
        else:
            return {
                "job_id": job_id,
                "status": status_payload.get("status", "TIMEOUT"),
                "warning": (
                    f"Job did not finish within {_MAX_POLL_ATTEMPTS * _POLL_INTERVAL_SECONDS / 60:.0f} min. "
                    "Use gnani_stt_batch_status to check later."
                ),
                "progress": status_payload.get("progress"),
            }

        final_status = status_payload.get("status", "")
        progress = status_payload.get("progress", {})

        if final_status == "START_FAILED":
            return {
                "job_id": job_id,
                "status": final_status,
                "error": status_payload.get("cancel_reason", "Job failed to start"),
            }

        if final_status == "FAILED":
            return {
                "job_id": job_id,
                "status": final_status,
                "progress": progress,
                "error": "All files failed. Check audio content — silence/tone-only audio is rejected.",
            }

        # ── Step 4: Get per-file results ────────────────────────────────
        await ctx.info("Job complete — fetching transcript URLs…")
        files_payload = await sc.client.get_json(
            f"{_BASE}/{job_id}/files",
            params={"status": "COMPLETED", "limit": 100},
        )

        # ── Step 5: Download transcripts ────────────────────────────────
        transcripts: list[dict[str, Any]] = []
        for file_entry in files_payload.get("data", []):
            transcript_url = file_entry.get("transcript_url")
            if not transcript_url:
                transcripts.append({
                    "file": file_entry.get("original_path"),
                    "status": file_entry.get("status"),
                    "error": file_entry.get("error_message"),
                })
                continue

            await ctx.info(f"Downloading transcript for {file_entry.get('original_path')}…")
            transcript_data = await sc.client.get_presigned(transcript_url)
            transcripts.append({
                "file": file_entry.get("original_path"),
                "file_id": file_entry.get("file_id"),
                "status": "COMPLETED",
                "language_code": transcript_data.get("language_code"),
                "duration_seconds": transcript_data.get("duration_seconds"),
                "full_transcript": transcript_data.get("full_transcript", ""),
                "segments": transcript_data.get("segments"),
            })

        return {
            "job_id": job_id,
            "status": final_status,
            "progress": progress,
            "transcripts": transcripts,
        }

    @mcp.tool(
        name="gnani_stt_batch_status",
        description=(
            "Check the status and progress of an existing Batch STT job.\n\n"
            "Returns the current status, progress counters, and job config. "
            "Does NOT return transcript text — call ``gnani_stt_batch_get_transcripts`` "
            "once the status is ``COMPLETED`` or ``PARTIAL_FAILURE``.\n\n"
            "Use this when ``gnani_stt_batch_transcribe`` timed out or when you "
            "submitted a job manually and want to check on it."
        ),
    )
    async def gnani_stt_batch_status(
        ctx: Context,
        job_id: str = Field(description="Job ID returned by gnani_stt_batch_transcribe or the Batch API."),
    ) -> dict[str, Any]:
        sc = await ready_ctx(ctx)
        payload = await sc.client.get_json(f"{_BASE}/{job_id}")
        return {
            "job_id": job_id,
            "status": payload.get("status"),
            "progress": payload.get("progress"),
            "config": payload.get("config"),
            "created_at": payload.get("created_at"),
            "started_at": payload.get("started_at"),
            "completed_at": payload.get("completed_at"),
            "cancel_reason": payload.get("cancel_reason"),
        }

    @mcp.tool(
        name="gnani_stt_batch_get_transcripts",
        description=(
            "Download the transcripts for a completed Batch STT job.\n\n"
            "Call this after ``gnani_stt_batch_status`` returns "
            "``COMPLETED`` or ``PARTIAL_FAILURE``. "
            "Returns ``full_transcript`` and per-segment data for each file.\n\n"
            "``transcript_url`` links expire after 1 hour — if download fails, "
            "call this tool again to get fresh URLs."
        ),
    )
    async def gnani_stt_batch_get_transcripts(
        ctx: Context,
        job_id: str = Field(description="Job ID of a completed batch job."),
    ) -> dict[str, Any]:
        sc = await ready_ctx(ctx)

        # Verify job is in a terminal state first.
        status_payload = await sc.client.get_json(f"{_BASE}/{job_id}")
        status = status_payload.get("status", "")
        if status not in _TERMINAL_STATUSES:
            return {
                "job_id": job_id,
                "status": status,
                "message": f"Job is not yet complete (current status: {status}). "
                           "Poll with gnani_stt_batch_status and retry when COMPLETED.",
            }

        files_payload = await sc.client.get_json(
            f"{_BASE}/{job_id}/files",
            params={"status": "COMPLETED", "limit": 100},
        )

        transcripts: list[dict[str, Any]] = []
        for file_entry in files_payload.get("data", []):
            transcript_url = file_entry.get("transcript_url")
            if not transcript_url:
                transcripts.append({
                    "file": file_entry.get("original_path"),
                    "status": file_entry.get("status"),
                    "error": file_entry.get("error_message"),
                })
                continue

            transcript_data = await sc.client.get_presigned(transcript_url)
            transcripts.append({
                "file": file_entry.get("original_path"),
                "file_id": file_entry.get("file_id"),
                "status": "COMPLETED",
                "language_code": transcript_data.get("language_code"),
                "duration_seconds": transcript_data.get("duration_seconds"),
                "full_transcript": transcript_data.get("full_transcript", ""),
                "segments": transcript_data.get("segments"),
            })

        return {
            "job_id": job_id,
            "status": status,
            "progress": status_payload.get("progress"),
            "transcripts": transcripts,
        }

    @mcp.tool(
        name="gnani_stt_batch_cancel",
        description=(
            "Cancel a running Batch STT job.\n\n"
            "Works for jobs in CREATED, STARTING, QUEUED, or IN_PROGRESS status. "
            "Has no effect on already-terminal jobs."
        ),
    )
    async def gnani_stt_batch_cancel(
        ctx: Context,
        job_id: str = Field(description="Job ID to cancel."),
    ) -> dict[str, Any]:
        sc = await ready_ctx(ctx)
        payload = await sc.client.post_json(f"{_BASE}/{job_id}/cancel", json_body={})
        return {
            "job_id": job_id,
            "status": payload.get("status"),
            "message": payload.get("message"),
        }
