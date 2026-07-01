"""Live scrobbling: parse push payloads (Plex webhook / generic JSON) into a
provider-agnostic ScrobbleEvent, keep a now-playing session row, and commit a
finished play to watch_events through the normal ingest path.

The parsing and decision helpers are pure (no DB) so they unit-test without a
live Postgres; handle_scrobble does the stateful work.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Optional

from ..db import connection
from ..util import normalize_text, now_utc
from .models import NormalizedEvent
from .normalize import _resolve_title, ingest_events
from .progress import recompute_title_progress

# Plex webhook event -> our coarse event name.
_PLEX_EVENTS = {
    "media.play": "play",
    "media.resume": "resume",
    "media.pause": "pause",
    "media.stop": "stop",
    "media.scrobble": "scrobble",   # Plex fires this once at ~90% watched
}
_STATE_BY_EVENT = {
    "play": "playing", "resume": "playing", "scrobble": "playing",
    "update": "playing",   # periodic real-time progress tick (no reset/re-commit)
    "pause": "paused", "stop": "stopped",
}
DEFAULT_THRESHOLD = 90


@dataclass
class ScrobbleEvent:
    """One push from a player, normalized across Plex / HA / AppleTV."""
    source: str                          # 'plex'|'homeassistant'|'appletv'|'generic'
    event: str                           # 'play'|'pause'|'resume'|'stop'|'scrobble'|'update'
    raw_title: str
    dedup_key: str
    account_label: str = ""
    platform_key: Optional[str] = None   # payload-supplied platform (e.g. 'netflix')
    kind: str = "movie"                  # 'movie' | 'series'
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_name: Optional[str] = None
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    progress_percent: Optional[float] = None
    position_seconds: Optional[int] = None
    duration_seconds: Optional[int] = None
    raw: dict = field(default_factory=dict)


# ── Pure parsers ────────────────────────────────────────────────────────────

def _int(value) -> Optional[int]:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _num(value) -> Optional[float]:
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _tmdb_from_guids(metadata: dict) -> Optional[int]:
    """Plex webhook Metadata.Guid is a list like [{'id': 'tmdb://693134'}]."""
    for g in metadata.get("Guid") or []:
        gid = (g or {}).get("id", "")
        if gid.startswith("tmdb://"):
            return _int(gid.split("tmdb://", 1)[1])
    return None


def _progress(position_s: Optional[int], duration_s: Optional[int]) -> Optional[float]:
    if position_s is None or not duration_s:
        return None
    pct = round(position_s / duration_s * 100, 2)
    return max(0.0, min(100.0, pct))


def parse_plex_payload(payload: dict) -> Optional[ScrobbleEvent]:
    """Map a Plex webhook payload (the JSON in the multipart `payload` field) to
    a ScrobbleEvent. Returns None for events/types we don't track."""
    event = _PLEX_EVENTS.get(payload.get("event", ""))
    if not event:
        return None
    meta = payload.get("Metadata") or {}
    mtype = meta.get("type")
    if mtype not in ("movie", "episode"):
        return None
    account = (payload.get("Account") or {}).get("title") or ""
    duration_ms = _int(meta.get("duration"))
    offset_ms = _int(meta.get("viewOffset"))
    duration_s = duration_ms // 1000 if duration_ms else None
    position_s = offset_ms // 1000 if offset_ms is not None else None
    # Plex sends no offset on the scrobble event — treat it as fully watched.
    progress = 100.0 if event == "scrobble" else _progress(position_s, duration_s)

    if mtype == "episode":
        rating_key = meta.get("grandparentRatingKey") or meta.get("ratingKey") or ""
        season = _int(meta.get("parentIndex"))
        episode = _int(meta.get("index"))
        return ScrobbleEvent(
            source="plex", event=event,
            account_label=account,
            raw_title=meta.get("grandparentTitle") or meta.get("title") or "",
            kind="series", season=season, episode=episode,
            episode_name=meta.get("title"),
            year=_int(meta.get("year")),
            tmdb_id=_tmdb_from_guids(meta),
            progress_percent=progress,
            position_seconds=position_s, duration_seconds=duration_s,
            dedup_key=f"plex:{rating_key}:{season}:{episode}",
            raw={"source": "plex", "ratingKey": meta.get("ratingKey")},
        )
    return ScrobbleEvent(
        source="plex", event=event,
        account_label=account,
        raw_title=meta.get("title") or "",
        kind="movie", year=_int(meta.get("year")),
        tmdb_id=_tmdb_from_guids(meta),
        progress_percent=progress,
        position_seconds=position_s, duration_seconds=duration_s,
        dedup_key=f"plex:{meta.get('ratingKey') or normalize_text(meta.get('title') or '')}",
        raw={"source": "plex", "ratingKey": meta.get("ratingKey")},
    )


def parse_generic_payload(body: dict) -> Optional[ScrobbleEvent]:
    """Map the documented JSON shape used by Home Assistant / AppleTV / Shortcuts.

    Shape: {event, source?, account?, platform?, title, kind?, year?, season?,
    episode?, episode_name?, tmdb_id?, progress_percent?, position_seconds?,
    duration_seconds?, dedup_key?}

    Accepted events: 'play', 'resume', 'pause', 'stop', 'scrobble', 'update'.
    'update' is a periodic real-time progress tick that refreshes the now-playing
    session without resetting it (unlike 'play'/'resume').
    """
    title = (body.get("title") or "").strip()
    if not title:
        return None
    event = (body.get("event") or "play").strip().lower()
    if event not in _STATE_BY_EVENT:
        return None
    source = (body.get("source") or "homeassistant").strip().lower()
    season = _int(body.get("season"))
    episode = _int(body.get("episode"))
    kind = (body.get("kind") or ("series" if episode is not None else "movie")).lower()
    position_s = _int(body.get("position_seconds"))
    duration_s = _int(body.get("duration_seconds"))
    progress = _num(body.get("progress_percent"))
    if progress is None:
        progress = _progress(position_s, duration_s)
    dedup = body.get("dedup_key") or \
        f"{source}:{normalize_text(title)}:{season}:{episode}"
    return ScrobbleEvent(
        source=source, event=event,
        account_label=(body.get("account") or "").strip(),
        platform_key=(body.get("platform") or None),
        raw_title=title, kind=kind, season=season, episode=episode,
        episode_name=body.get("episode_name"),
        year=_int(body.get("year")), tmdb_id=_int(body.get("tmdb_id")),
        progress_percent=progress,
        position_seconds=position_s, duration_seconds=duration_s,
        dedup_key=str(dedup),
        raw={"source": source, **({"platform": body["platform"]} if body.get("platform") else {})},
    )


# ── Pure decision helpers ───────────────────────────────────────────────────

def state_for_event(event: str) -> str:
    return _STATE_BY_EVENT.get(event, "playing")


def should_commit(evt: ScrobbleEvent, threshold: float) -> bool:
    """A play becomes a permanent watch_event when Plex fires `scrobble`, or when
    progress reaches the commit threshold (>=90% by default)."""
    if evt.event == "scrobble":
        return True
    if evt.progress_percent is not None and evt.progress_percent >= threshold:
        return True
    return False


def should_reset_commit(evt: ScrobbleEvent, threshold: float) -> bool:
    """Whether a play/resume should be treated as a *fresh* viewing and clear any
    prior commit on the session.

    Players like Home Assistant / AppleTV poll and re-send `play` every few seconds
    during continuous playback. We must NOT keep clearing the commit on those polls
    once a session has already crossed the watched threshold — otherwise a stream
    that reaches 90% briefly commits, then the next poll un-commits it, so it lingers
    in Now Playing and is never reliably registered (and can re-commit as a duplicate).

    A genuine replay starts near 0%, well below the threshold; an ongoing high-progress
    stream is not a restart. So only reset when progress is still below the threshold."""
    if evt.event not in ("play", "resume"):
        return False
    return (evt.progress_percent or 0) < threshold


# ── Stateful handling ───────────────────────────────────────────────────────

def _resolve_provider_id(cur, evt: ScrobbleEvent) -> Optional[str]:
    """Attribute to the payload-supplied platform if known, else fall back to the
    source provider (plex / homeassistant / appletv); finally the 'generic' row."""
    for key in (evt.platform_key, evt.source, "generic"):
        if not key:
            continue
        cur.execute("SELECT id FROM providers WHERE key = %s", (key,))
        row = cur.fetchone()
        if row:
            return row["id"]
    return None


def _resolve_profile_id(cur, household_id: str, evt: ScrobbleEvent,
                        token_user_id: str) -> Optional[str]:
    """Map an incoming account label to a household profile; fall back to the
    token's own user when no mapping exists."""
    if evt.account_label:
        cur.execute(
            "SELECT user_id FROM scrobble_account_map "
            "WHERE household_id = %s AND source = %s AND account_label = %s",
            (household_id, evt.source, evt.account_label),
        )
        row = cur.fetchone()
        if row:
            return row["user_id"]
    return token_user_id


def _resolve_session_title(cur, evt: ScrobbleEvent) -> tuple[Optional[str], bool]:
    """Find (or create) the central film/series title for a live session so the
    now-playing card can show *its* poster (not the episode's). Series resolve by
    normalized show title only — an episode's own tmdb_id is not the show's, so it
    must never be written onto the series title. Movies resolve by tmdb_id then
    normalized title. Mirrors the ingest matcher (`_resolve_title`)."""
    title = (evt.raw_title or "").strip()
    if not title:
        return None, False
    if evt.kind == "series":
        return _resolve_title(cur, "series", title, None, None, {})
    return _resolve_title(cur, "movie", title, evt.year, evt.tmdb_id, {})


def _maybe_enqueue_enrich(cur, title_id: str) -> None:
    """Queue TMDB enrichment for a freshly-seen title so its poster shows up while
    it is still playing — unless it is already enriched or a job is pending."""
    cur.execute(
        "INSERT INTO background_jobs (kind, payload) "
        "SELECT 'enrich_title', %s::jsonb "
        "WHERE EXISTS (SELECT 1 FROM titles WHERE id = %s AND enriched_at IS NULL) "
        "  AND NOT EXISTS (SELECT 1 FROM background_jobs WHERE kind = 'enrich_title' "
        "    AND payload->>'title_id' = %s AND status = 'pending')",
        (json.dumps({"title_id": str(title_id)}), str(title_id), str(title_id)),
    )


def handle_scrobble(household_id: str, evt: ScrobbleEvent, token_user_id: str,
                    threshold: float = DEFAULT_THRESHOLD) -> dict:
    """UPSERT the now-playing session and commit it to watch_events when finished.
    Returns a small summary describing what happened."""
    state = state_for_event(evt.event)
    commit = should_commit(evt, threshold)
    committed = False
    with connection() as conn, conn.cursor() as cur:
        # Fail fast instead of hanging forever if this path ever contends on a
        # row/index lock (defense-in-depth; the structural fix is threading the
        # cursor into ingest_events below so the whole commit is one transaction).
        cur.execute("SET LOCAL lock_timeout = '5s'")
        provider_id = _resolve_provider_id(cur, evt)
        user_id = _resolve_profile_id(cur, household_id, evt, token_user_id)
        # A fresh `play`/`resume` *below the threshold* starts a new session; a
        # play poll on an already-watched stream must not clear the prior commit.
        reset_commit = should_reset_commit(evt, threshold)
        cur.execute(
            "INSERT INTO scrobble_sessions "
            "(household_id, user_id, provider_id, source, account_label, platform_key, "
            " raw_title, kind, season, episode, episode_name, year, tmdb_id, "
            " progress_percent, position_seconds, duration_seconds, state, dedup_key, raw) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (household_id, source, account_label, dedup_key) DO UPDATE SET "
            "  user_id = EXCLUDED.user_id, provider_id = EXCLUDED.provider_id, "
            "  platform_key = EXCLUDED.platform_key, progress_percent = EXCLUDED.progress_percent, "
            "  position_seconds = EXCLUDED.position_seconds, duration_seconds = EXCLUDED.duration_seconds, "
            "  state = EXCLUDED.state, year = COALESCE(EXCLUDED.year, scrobble_sessions.year), "
            "  tmdb_id = COALESCE(EXCLUDED.tmdb_id, scrobble_sessions.tmdb_id), "
            "  kind = EXCLUDED.kind, season = EXCLUDED.season, "
            "  episode = EXCLUDED.episode, episode_name = EXCLUDED.episode_name, "
            "  updated_at = now(), "
            "  committed_at = CASE WHEN %s THEN NULL ELSE scrobble_sessions.committed_at END "
            "RETURNING id, committed_at",
            (household_id, user_id, provider_id, evt.source, evt.account_label,
             evt.platform_key, evt.raw_title, evt.kind, evt.season, evt.episode,
             evt.episode_name, evt.year, evt.tmdb_id,
             evt.progress_percent or 0, evt.position_seconds, evt.duration_seconds,
             state, evt.dedup_key, json.dumps(evt.raw), reset_commit),
        )
        row = cur.fetchone()
        session_id = row["id"]
        already_committed = row["committed_at"] is not None

        # Resolve (or create) the central title so the now-playing card can show
        # the series/movie poster, and kick off enrichment for fresh content so
        # the poster appears while it is still playing.
        title_id, _created = _resolve_session_title(cur, evt)
        if title_id:
            cur.execute("UPDATE scrobble_sessions SET title_id = %s WHERE id = %s",
                        (title_id, session_id))
            _maybe_enqueue_enrich(cur, title_id)

        if commit and not already_committed and user_id and provider_id:
            ne = NormalizedEvent(
                raw_title=evt.episode_name or evt.raw_title,
                clean_title=evt.raw_title,
                watched_at=now_utc(),
                kind="series" if evt.kind == "series" else "movie",
                year=evt.year, season=evt.season, episode=evt.episode,
                episode_name=evt.episode_name,
                duration_seconds=evt.duration_seconds,
                progress_percent=evt.progress_percent,
                completed=True, tmdb_id=evt.tmdb_id,
                raw={"source": evt.source, "scrobble": True},
            )
            # Commit on the SAME open cursor/transaction. Opening a second pooled
            # connection here would block forever: this transaction may hold an
            # uncommitted INSERT on the titles unique index (a first-seen title),
            # and a second connection re-resolving that title would wait on the
            # lock while this one waits in Python for it to return — a self-deadlock
            # invisible to Postgres's detector.
            ingest_events(str(user_id), str(provider_id), None, [ne], cur=cur)
            # Mark committed but keep the live state: an `update`/`play`/`scrobble`
            # tick maps to 'playing', so the now-playing card stays visible while
            # playback continues past the threshold. The card only disappears when a
            # real `stop` event flips state to 'stopped'. The already_committed guard
            # ensures later ticks see committed_at and do NOT re-ingest.
            cur.execute(
                "UPDATE scrobble_sessions SET committed_at = now() WHERE id = %s",
                (session_id,))
            committed = True

        # Keep the precomputed completion status in sync with live playback: a
        # movie/series that's playing but not yet committed shows as in-progress,
        # and a just-committed play flips it to finished (series: once all
        # episodes are in). Runs on the same open cursor/transaction.
        if user_id and title_id:
            recompute_title_progress(cur, str(user_id), str(title_id))

    return {
        "session_id": str(session_id),
        "state": state,
        "committed": committed,
        "mapped_profile": bool(user_id),
        "provider_id": str(provider_id) if provider_id else None,
    }


def expire_stale_sessions(idle_minutes: int = 30,
                          threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Worker tick: sessions with no update for `idle_minutes` are marked stopped;
    those that reached the threshold but never got a stop/scrobble webhook are
    committed now. Old committed sessions are pruned. Returns counts."""
    committed = 0
    expired = 0
    with connection() as conn, conn.cursor() as cur:
        # Committed-but-still-playing sessions now keep state='playing' (so the card
        # stays visible). Include them here: if their ticks silently stop (no stop
        # event ever arrives, e.g. TV unplugged) they must still be retired from
        # now-playing. The commit branch is guarded on committed_at IS NULL so an
        # already-committed stale session is only marked stopped (no second ingest).
        cur.execute(
            "SELECT * FROM scrobble_sessions "
            "WHERE state <> 'stopped' "
            "AND updated_at < now() - (%s || ' minutes')::interval",
            (str(idle_minutes),),
        )
        stale = cur.fetchall()
        for s in stale:
            expired += 1
            progress = float(s["progress_percent"] or 0)
            if (s["committed_at"] is None and progress >= threshold
                    and s["user_id"] and s["provider_id"]):
                ne = NormalizedEvent(
                    raw_title=s["episode_name"] or s["raw_title"],
                    clean_title=s["raw_title"],
                    watched_at=now_utc(),
                    kind="series" if s["kind"] == "series" else "movie",
                    year=s["year"], season=s["season"], episode=s["episode"],
                    episode_name=s["episode_name"],
                    duration_seconds=s["duration_seconds"],
                    progress_percent=progress, completed=True,
                    tmdb_id=s["tmdb_id"], raw={"source": s["source"], "scrobble": True},
                )
                # Same-transaction commit (see handle_scrobble): a first-seen title
                # committed during expiry must not re-resolve on a second connection.
                ingest_events(str(s["user_id"]), str(s["provider_id"]), None, [ne], cur=cur)
                cur.execute("UPDATE scrobble_sessions SET committed_at = now(), "
                            "state = 'stopped' WHERE id = %s", (s["id"],))
                committed += 1
            else:
                cur.execute("UPDATE scrobble_sessions SET state = 'stopped' "
                            "WHERE id = %s", (s["id"],))
        # Drop committed/stopped sessions older than a day to keep the table lean.
        cur.execute(
            "DELETE FROM scrobble_sessions "
            "WHERE committed_at IS NOT NULL AND committed_at < now() - interval '1 day'")
    return {"expired": expired, "committed": committed}
