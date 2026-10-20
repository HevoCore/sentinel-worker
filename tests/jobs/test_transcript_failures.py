"""Transcript fail reasons keep captcha distinct from no-captions / billing."""

from __future__ import annotations

import sys
from pathlib import Path

SCRAPE_WORKER = Path(__file__).resolve().parents[2] / "scrape_worker"
if str(SCRAPE_WORKER) not in sys.path:
    sys.path.insert(0, str(SCRAPE_WORKER))

from jobs.transcript import TranscriptError, _combine_transcript_failures


def test_captcha_plus_unpaid_is_captcha_blocked_not_no_captions():
    primary = TranscriptError(
        "YouTube captcha / sorry page blocked the watch request",
        reason="captcha_blocked",
        rate_limited=True,
        blocked=True,
    )
    fallback = TranscriptError(
        'TranscriptAPI returned 402: {"detail":{"message":"You don’t have an active paid plan yet."}}',
        reason="provider_unpaid",
    )
    combined = _combine_transcript_failures(primary, fallback)
    assert combined.reason == "captcha_blocked"
    assert combined.blocked is True
    assert combined.rate_limited is True
    assert "no_captions" not in combined.reason
    assert combined.providers["innertube"]["reason"] == "captcha_blocked"
    assert combined.providers["transcriptapi"]["reason"] == "provider_unpaid"
    assert "402" in str(combined)


def test_both_no_captions_stays_no_captions():
    primary = TranscriptError("YouTube get_panel returned no transcript cues", reason="no_captions")
    fallback = TranscriptError("TranscriptAPI returned 404: missing", reason="no_captions")
    combined = _combine_transcript_failures(primary, fallback)
    assert combined.reason == "no_captions"
    assert combined.blocked is False
    assert combined.rate_limited is False


def test_captcha_plus_no_captions_api_is_still_captcha():
    """A 404 after captcha is not proof YouTube had no captions."""
    primary = TranscriptError(
        "YouTube captcha / sorry page blocked the watch request",
        reason="captcha_blocked",
        blocked=True,
        rate_limited=True,
    )
    fallback = TranscriptError("TranscriptAPI returned 404: missing", reason="no_captions")
    combined = _combine_transcript_failures(primary, fallback)
    assert combined.reason == "captcha_blocked"
    assert combined.blocked is True
