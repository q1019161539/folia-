"""Who a song *is*, kept apart from which lyric sheet happened to match it.

A lyric candidate used to be allowed to rename the job it matched. That closed a
loop with teeth: the candidate's title overwrote job.title, the next re-run
searched with that overwritten title, the pool degenerated to near-miss titles,
and the same wrong candidate won again. An audit of 46 finished songs found 21
whose identity had been rewritten this way -- every single title that ever
changed had changed into a candidate's title -- and 7 of 9 songs that looked
"line-only" actually had verbatim releases waiting under their original name.

So identity has exactly one owner. The identification stage (DeepSeek's reading
of the full-recording ASR, or an audio fingerprint from Shazam / ACRCloud) writes
`identified_title` / `identified_artist`. Lyric search, candidate scoring,
alignment and rendering all read them and none of them may write. What a
candidate knows about itself lives in the report under `matched_*`, where it can
be inspected without pretending to be the song's name.
"""
from __future__ import annotations

from typing import Any

# Everything allowed to name a song. Recognition only: a lyric candidate is
# absent because it identifies a lyric sheet rather than a performance, and a
# human is absent because "which lyric sheet looks right" is the same judgement
# wearing a different hat -- letting it through the manual page would reopen the
# loop by hand. Future automatic fusion of recognisers belongs here; nothing else
# does.
IDENTITY_SOURCES = ("shazam", "acrcloud", "deepseek", "automation_history_backfill", "legacy_fallback")
FINGERPRINT_SOURCES = ("shazam", "acrcloud")


def identity_fields(title: str, artist: str = "", source: str = "") -> dict[str, Any]:
    """The columns an identification stage is allowed to write."""
    if source and source not in IDENTITY_SOURCES:
        raise ValueError(f"未知的歌曲身份来源：{source}")
    return {
        "identified_title": str(title or "").strip(),
        "identified_artist": str(artist or "").strip(),
        "identity_source": source,
    }


def matched_candidate_fields(candidate: dict[str, Any] | None) -> dict[str, Any]:
    """What the winning lyric sheet calls itself -- reported, never applied."""
    candidate = candidate or {}
    return {
        "matched_title": str(candidate.get("title") or ""),
        "matched_artist": str(candidate.get("artist") or ""),
        "matched_album": str(candidate.get("album") or ""),
        "matched_source": str(candidate.get("platform") or ""),
        "matched_candidate_id": str(candidate.get("candidate_id") or ""),
    }


def resolve_search_identity(job: dict[str, Any]) -> dict[str, Any]:
    """The name every lyric search must start from.

    A job written since this change carries its own identity. One from before it
    falls back to the display title so old projects keep working, but the report
    says so out loud: `legacy_fallback` is the marker that this query may be
    running on a title a candidate wrote.
    """
    title = str(job.get("identified_title") or "").strip()
    artist = str(job.get("identified_artist") or "").strip()
    if title:
        source = str(job.get("identity_source") or "").strip() or "legacy_fallback"
        return {"title": title, "artist": artist, "source": source}
    return {
        "title": str(job.get("title") or "").strip(),
        "artist": str(job.get("artist") or "").strip(),
        "source": "legacy_fallback",
    }


def fingerprint_identity(match: dict[str, Any] | None) -> dict[str, Any] | None:
    """The fingerprint verdict a finished run already recorded, if there was one."""
    match = match or {}
    for provider_key, title_key in (
        ("song_identity_primary_provider", "song_identity_primary_title"),
        ("song_identity_secondary_provider", "song_identity_secondary_title"),
    ):
        provider = str(match.get(provider_key) or "").strip().lower()
        title = str(match.get(title_key) or "").strip()
        if provider in FINGERPRINT_SOURCES and title:
            return {"title": title, "source": provider}
    return None


def backfill_identity(
    job: dict[str, Any], original: dict[str, Any] | None, match: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Recover identity for a job written before the identity columns existed.

    A fingerprint outranks the automation stage's guess, because that is exactly
    the correction the fingerprint exists to make: 《很任性》 was guessed 人人心 off
    a misheard chorus and Shazam put it right. Replaying the automation record
    blindly would reinstate the wrong name as this song's trusted identity.

    Where nothing can be recovered this returns None rather than promoting the
    current title: that title is what may have been overwritten, and writing it
    into `identified_title` would launder a polluted name into the trusted field.
    """
    if str(job.get("identified_title") or "").strip():
        return None
    hit = fingerprint_identity(match)
    if hit:
        return identity_fields(hit["title"], "", hit["source"])
    title = str((original or {}).get("title") or "").strip()
    if not title:
        return None
    return identity_fields(title, str((original or {}).get("artist") or ""), "automation_history_backfill")
