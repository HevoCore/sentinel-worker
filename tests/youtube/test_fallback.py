"""Calendar overlay / fallback and facade regression tests."""

from __future__ import annotations

from datetime import datetime

import pytz

from youtube_core.models import StreamCard
from youtube_core.service import YouTubeService
from utils.youtube import Youtube as UtilsYoutube
from schedule.library.youtube import Youtube


def test_youtube_table_includes_live_and_upcoming(monkeypatch):
    yt = Youtube()

    def fake_classify(url, timezone="America/New_York"):
        return {
            "live": [
                {
                    "status": "live",
                    "video_id": "4KI8Tcym7kM",
                    "video_title": "County Board",
                    "meeting_link": "https://www.youtube.com/watch?v=4KI8Tcym7kM",
                    "published_time": "2026-09-02T18:00:00Z",
                }
            ],
            "upcoming": [
                {
                    "status": "upcoming",
                    "video_id": "upcoming0001",
                    "video_title": "Next Week",
                    "meeting_link": "https://www.youtube.com/watch?v=upcoming0001",
                    "scheduled_time": "2026-09-10T18:00:00Z",
                }
            ],
            "concluded": [
                {
                    "status": "concluded",
                    "video_id": "oldVideo0001",
                    "video_title": "Last Week",
                    "meeting_link": "https://www.youtube.com/watch?v=oldVideo0001",
                }
            ],
            "fetch_ok": True,
        }

    monkeypatch.setattr(yt, "classify_channel_streams", fake_classify)
    meetings = yt.youtube_table("https://www.youtube.com/@arlingtoncountyTV/streams")
    statuses = {m["Status"] for m in meetings}
    assert statuses == {"Live", "Upcoming"}
    live = next(m for m in meetings if m["Status"] == "Live")
    assert live["video_id"] == "4KI8Tcym7kM"
    assert "4KI8Tcym7kM" in (live.get("Meeting link") or "")


def test_youtube_table_raises_on_fetch_failure(monkeypatch):
    yt = Youtube()
    monkeypatch.setattr(
        yt,
        "classify_channel_streams",
        lambda *a, **k: {
            "live": [],
            "upcoming": [],
            "concluded": [],
            "fetch_ok": False,
            "fetch_error": "ytInitialData missing or unreadable",
        },
    )
    try:
        yt.youtube_table("https://www.youtube.com/@x/streams")
    except RuntimeError as exc:
        assert "ytInitialData" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_apply_schedule_fallback_require_title_match(monkeypatch):
    yt = YouTubeService()

    def fake_classify(channel_url, timezone="America/New_York"):
        return {
            "live": [],
            "upcoming": [],
            "concluded": [
                {
                    "status": "concluded",
                    "video_id": "goodVideo01",
                    "video_title": "Finance and Appropriations",
                    "meeting_link": "https://www.youtube.com/watch?v=goodVideo01",
                    "published_time": "2026-07-30T12:00:00Z",
                },
                {
                    "status": "concluded",
                    "video_id": "badVideo000",
                    "video_title": "Unrelated Zoning Hearing",
                    "meeting_link": "https://www.youtube.com/watch?v=badVideo000",
                    "published_time": "2026-07-30T12:00:00Z",
                },
            ],
            "skipped": [],
            "channel_url": channel_url,
            "streams_url": channel_url,
            "videos_url": channel_url.replace("/streams", "/videos"),
            "fetch_ok": True,
        }

    monkeypatch.setattr(yt, "classify_channel_for_fallback", fake_classify)

    meetings = [
        {
            "Meeting name": "Finance and Appropriations",
            "Scheduled time": "2026-07-30T18:00:00Z",
            "Status": "Upcoming",
        }
    ]
    out = yt.apply_schedule_fallback(
        meetings,
        channel_url="https://www.youtube.com/@x/streams",
        timezone="America/New_York",
        require_title_match=True,
        title_match_threshold=0.3,
        max_meeting_age_hours=10000,  # fixture date must stay eligible for date-match
    )
    result_meetings = out["meetings"] if isinstance(out, dict) else out
    assert result_meetings
    hit = result_meetings[0]
    assert hit.get("video_id") == "goodVideo01"
    assert "Meeting link" in hit


def test_same_day_sole_meeting_attaches_live_without_title_match(monkeypatch):
    yt = YouTubeService()
    tz = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    scheduled = now.replace(hour=18, minute=0, second=0, microsecond=0).astimezone(
        pytz.UTC
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    def fake_classify(channel_url, timezone="America/New_York"):
        return {
            "live": [
                {
                    "status": "live",
                    "video_id": "liveVideo01",
                    "video_title": "WUTV Government",
                    "meeting_link": "https://www.youtube.com/watch?v=liveVideo01",
                    "published_time": scheduled,
                    "source_tab": "streams",
                }
            ],
            "upcoming": [],
            "concluded": [],
            "skipped": [],
            "channel_url": channel_url,
            "fetch_ok": True,
        }

    monkeypatch.setattr(yt, "classify_channel_for_fallback", fake_classify)
    out = yt.apply_schedule_fallback(
        [
            {
                "Meeting name": "City Council Regular Meeting",
                "Scheduled time": scheduled,
                "Status": "Upcoming",
            }
        ],
        channel_url="https://www.youtube.com/@x/streams",
        timezone="America/New_York",
        require_title_match=True,
        title_match_threshold=0.3,
        max_meeting_age_hours=24,
    )
    meetings = out["meetings"]
    assert len(meetings) == 1
    assert meetings[0]["Status"] == "Live"
    assert meetings[0]["video_id"] == "liveVideo01"


def test_unmatched_live_is_stubbed_when_multiple_same_day_meetings(monkeypatch):
    yt = YouTubeService()
    tz = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    scheduled = now.replace(hour=18, minute=0, second=0, microsecond=0).astimezone(
        pytz.UTC
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    def fake_classify(channel_url, timezone="America/New_York"):
        return {
            "live": [
                {
                    "status": "live",
                    "video_id": "liveVideo02",
                    "video_title": "Random Live Stream",
                    "meeting_link": "https://www.youtube.com/watch?v=liveVideo02",
                    "published_time": scheduled,
                    "source_tab": "streams",
                }
            ],
            "upcoming": [],
            "concluded": [],
            "skipped": [],
            "channel_url": channel_url,
            "fetch_ok": True,
        }

    monkeypatch.setattr(yt, "classify_channel_for_fallback", fake_classify)
    out = yt.apply_schedule_fallback(
        [
            {
                "Meeting name": "Planning Commission",
                "Scheduled time": scheduled,
                "Status": "Upcoming",
            },
            {
                "Meeting name": "Zoning Board",
                "Scheduled time": scheduled,
                "Status": "Upcoming",
            },
        ],
        channel_url="https://www.youtube.com/@x/streams",
        timezone="America/New_York",
        require_title_match=True,
        title_match_threshold=0.3,
        max_meeting_age_hours=24,
    )
    meetings = out["meetings"]
    lives = [m for m in meetings if m.get("Status") == "Live"]
    assert len(lives) == 1
    assert lives[0]["video_id"] == "liveVideo02"
    assert lives[0]["Meeting name"] == "Random Live Stream"


def test_overlay_fetch_failure_is_not_youtube_used(monkeypatch):
    yt = YouTubeService()

    def fake_classify(channel_url, timezone="America/New_York"):
        return {
            "live": [],
            "upcoming": [],
            "concluded": [],
            "skipped": [],
            "channel_url": channel_url,
            "fetch_ok": False,
            "fetch_error": "ytInitialData missing or unreadable",
        }

    monkeypatch.setattr(yt, "classify_channel_for_fallback", fake_classify)
    primary = [
        {
            "Meeting name": "Council",
            "Scheduled time": "2026-09-03T18:00:00Z",
            "Status": "Upcoming",
        }
    ]
    out = yt.apply_schedule_fallback(
        primary,
        channel_url="https://www.youtube.com/@x/streams",
        timezone="America/New_York",
    )
    assert out["youtube_used"] is False
    assert out["fetch_ok"] is False
    assert out["meetings"] == primary
    assert out["live_count"] == 0


def test_utils_facade_get_live_videos_uses_core(monkeypatch):
    calls = {}

    def fake_get_live_videos(self, channel_url=None, soup=None):
        calls["channel_url"] = channel_url
        calls["soup"] = soup is not None
        return [{"video_id": "liveVideo001", "video_title": "Live"}]

    monkeypatch.setattr(YouTubeService, "get_live_videos", fake_get_live_videos)
    utils = UtilsYoutube(
        url="https://www.youtube.com/@Handle/streams", meeting_title="Council"
    )
    live = utils.get_live_videos(soup=object())
    assert live == [{"video_id": "liveVideo001", "video_title": "Live"}]
    assert calls["soup"] is True


def test_stream_card_roundtrip():
    card = StreamCard.from_dict(
        {
            "video_id": "abcdefghijk",
            "video_title": "Council",
            "status": "live",
            "meeting_link": "https://www.youtube.com/watch?v=abcdefghijk",
            "published_time": "2026-07-30T12:00:00Z",
        }
    )
    assert card.to_dict()["published_time"] == "2026-07-30T12:00:00Z"


def test_live_started_at_uses_player_start_timestamp(monkeypatch):
    yt = YouTubeService()
    monkeypatch.setattr(yt, "_fetch_youtube_initial_data", lambda url: {"contents": {}})
    monkeypatch.setattr(
        yt.client,
        "get_player_response",
        lambda url: {
            "microformat": {
                "playerMicroformatRenderer": {
                    "publishDate": "2023-12-01",
                    "liveBroadcastDetails": {
                        "startTimestamp": "2026-09-02T18:00:00+00:00",
                        "isLiveNow": True,
                    },
                }
            }
        },
    )
    started = yt.get_live_started_at("4KI8Tcym7kM")
    assert started is not None
    assert started.year == 2026
    assert started.month == 9


def test_live_started_at_missing_timestamp_is_not_stale(monkeypatch):
    yt = YouTubeService()
    monkeypatch.setattr(
        yt,
        "_fetch_youtube_initial_data",
        lambda url: {"contents": "Started streaming on Dec 1, 2023"},
    )
    monkeypatch.setattr(yt.client, "get_player_response", lambda url: None)
    assert yt.get_live_started_at("abcdefghijk") is None
