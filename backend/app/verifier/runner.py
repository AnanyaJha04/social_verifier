import asyncio
import json
import logging
import tempfile
from pathlib import Path

from app.core import db
from app.core.config import settings
from app.core.telemetry import record_stage
from app.rag import claim_store, gov_store
from app.verifier.claims import (
    ClaimVerification,
    extract_claims,
    generate_conclusion,
    verify_claim,
    verify_claim_to_dict,
)
from app.verifier.clip_match import attach_clip_times
from app.verifier.download import download_clip, extract_audio
from app.verifier.manuscript import build_manuscript

logger = logging.getLogger(__name__)


def _prior_context(check_id: str, claim_index: int, query_text: str) -> list[str]:
    """Best-effort retrieval from Qdrant -- claim verification must keep
    working even if Qdrant isn't configured or is briefly unreachable, it
    just loses the cross-claim context in that case."""
    if not settings.qdrant_url:
        return []
    try:
        return claim_store.search_prior_context(check_id, claim_index, query_text)
    except Exception:
        logger.exception("Prior-claim context retrieval failed for %s claim %d", check_id, claim_index)
        return []


def _gov_context(query_text: str) -> list[dict]:
    """Best-effort retrieval from the indexed Indian-government source
    corpus (see app/rag/gov_store.py, populated by
    scripts/ingest_gov_sources.py) -- claim verification must keep working
    even if Qdrant isn't configured, the gov corpus hasn't been ingested
    yet, or is briefly unreachable; it just loses that grounding in that
    case, mirroring _prior_context above."""
    if not settings.qdrant_url:
        return []
    try:
        return gov_store.search_gov_sources(query_text)
    except Exception:
        logger.exception("Gov-source retrieval failed for query %r", query_text)
        return []


def _index_claim(check_id: str, claim_index: int, verification: ClaimVerification) -> None:
    if not settings.qdrant_url:
        return
    try:
        claim_store.index_claim(
            check_id, claim_index, verification.quote, verification.claim, verification.analysis,
        )
    except Exception:
        logger.exception("Indexing claim %d into Qdrant failed for %s", claim_index, check_id)


def _set_status(check_id: str, status: str, progress: str = "") -> None:
    db.execute(
        "UPDATE reel_checks SET status=?, progress=? WHERE id=?",
        (status, progress, check_id),
    )


async def run_reel_check(check_id: str, url: str) -> None:
    """One-shot background pipeline: download -> transcribe -> extract
    claims -> verify each claim. Runs as a detached asyncio task kicked off
    by the API endpoint; all state lives in the reel_checks row so the
    frontend can poll it, mirroring the live-session status pattern."""
    try:
        # The source video is downloaded into a permanent, per-check
        # directory (not the temp dir below) so a clip of each claim's
        # exact quote can still be cut on demand after this pipeline
        # finishes -- everything else here is transient working data.
        check_dir = settings.data_dir / "reel_checks" / check_id
        _set_status(check_id, "downloading")
        with record_stage(check_id, "downloading"):
            video_path = await asyncio.to_thread(download_clip, url, check_dir)

        with tempfile.TemporaryDirectory(prefix="reel_check_") as tmp:
            tmp_dir = Path(tmp)

            _set_status(check_id, "transcribing")
            raw_audio = tmp_dir / "audio_raw.wav"
            processed_audio = tmp_dir / "audio_dsp.wav"
            with record_stage(check_id, "transcribing"):
                await asyncio.to_thread(extract_audio, video_path, raw_audio)
                manuscript, segments = await asyncio.to_thread(
                    build_manuscript, raw_audio, processed_audio
                )

            db.execute("UPDATE reel_checks SET manuscript=? WHERE id=?", (manuscript, check_id))

            _set_status(check_id, "extracting_claims")
            with record_stage(check_id, "extracting_claims"):
                claims = await asyncio.to_thread(extract_claims, manuscript)
            claims = attach_clip_times(claims, segments)

            verifications: list[ClaimVerification] = []
            verification_dicts = []
            for i, claim in enumerate(claims):
                _set_status(check_id, "verifying_claims", f"{i + 1}/{len(claims)}")
                prior_context = await asyncio.to_thread(
                    _prior_context, check_id, i, f"{claim.claim} {claim.quote}",
                )
                gov_hits = await asyncio.to_thread(_gov_context, f"{claim.claim} {claim.quote}")
                with record_stage(check_id, f"verifying_claims"):
                    verification = await asyncio.to_thread(
                        verify_claim, claim, prior_context, gov_hits
                    )
                verifications.append(verification)
                verification_dicts.append(verify_claim_to_dict(verification))
                await asyncio.to_thread(_index_claim, check_id, i, verification)
                # Persist incrementally so a slow/failed later claim doesn't
                # lose already-verified ones, and the frontend can show
                # results as they arrive instead of only at the very end.
                db.execute(
                    "UPDATE reel_checks SET claims_json=? WHERE id=?",
                    (json.dumps(verification_dicts), check_id),
                )

            _set_status(check_id, "concluding")
            with record_stage(check_id, "concluding"):
                conclusion = await asyncio.to_thread(generate_conclusion, verifications)
            db.execute("UPDATE reel_checks SET conclusion=? WHERE id=?", (conclusion, check_id))

            db.execute(
                "UPDATE reel_checks SET status='done', progress='', completed_at=datetime('now') "
                "WHERE id=?",
                (check_id,),
            )
    except Exception as e:
        logger.exception("Reel check %s failed", check_id)
        db.execute(
            "UPDATE reel_checks SET status='error', error_message=?, completed_at=datetime('now') "
            "WHERE id=?",
            (str(e), check_id),
        )
