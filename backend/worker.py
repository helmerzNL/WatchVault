"""Background worker: processes the background_jobs queue.

Handles metadata enrichment and provider syncs, and periodically schedules
syncs for enabled API connections. Uses FOR UPDATE SKIP LOCKED so multiple
workers can run safely.
"""
from __future__ import annotations

import json
import time
import traceback

from app.db import connection
from app.plugins import enrich_person, enrich_title

POLL_INTERVAL = 3          # seconds between queue polls
SCHEDULE_INTERVAL = 900    # enqueue connection syncs every 15 min
EXPIRE_INTERVAL = 60       # sweep stale scrobble sessions every minute
EXPIRE_AFTER_MINUTES = 10  # no update in this long -> stop the live session


def _claim_job():
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM background_jobs "
            "WHERE status = 'pending' AND run_after <= now() "
            "ORDER BY run_after FOR UPDATE SKIP LOCKED LIMIT 1"
        )
        job = cur.fetchone()
        if job:
            cur.execute(
                "UPDATE background_jobs SET status='running', attempts=attempts+1, "
                "updated_at=now() WHERE id = %s", (job["id"],))
        return job


def _finish(job_id, status, result=None, error=None):
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE background_jobs SET status=%s, result=%s, last_error=%s, updated_at=now() "
            "WHERE id = %s",
            (status, json.dumps(result) if result else None, error, job_id),
        )


def _retry_or_fail(job, error):
    final = "error" if job["attempts"] >= job["max_attempts"] else "pending"
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE background_jobs SET status=%s, last_error=%s, "
            "run_after = now() + interval '60 seconds', updated_at=now() WHERE id = %s",
            (final, error, job["id"]),
        )


def _handle(job) -> dict:
    kind = job["kind"]
    payload = job["payload"] or {}
    if kind == "enrich_title":
        return enrich_title(payload["title_id"])
    if kind == "enrich_person":
        return enrich_person(payload["person_id"])
    if kind == "sync_connection":
        return _run_sync(payload["connection_id"])
    if kind == "trakt_title_sync":
        from app.ingest import ingest_title_from_trakt
        return ingest_title_from_trakt(
            payload["user_id"], payload["household_id"], payload["title_id"])
    if kind == "reattribute_trakt_all":
        from app.networks import reattribute_all_trakt
        return reattribute_all_trakt()
    return {"status": "unknown_kind"}


def _run_sync(connection_id: str) -> dict:
    from app.ingest import ingest_events, prune_connection_libraries, enqueue_trakt_title_syncs
    from app.ingest.adapters import get_adapter
    from app.db import query_one, execute
    conn = query_one(
        "SELECT sc.*, p.adapter, p.id AS provider_id FROM source_connections sc "
        "JOIN providers p ON p.id = sc.provider_id WHERE sc.id = %s AND sc.enabled",
        (connection_id,),
    )
    if not conn:
        return {"status": "skipped"}
    owner = query_one(
        "SELECT id FROM users WHERE household_id = %s AND deleted_at IS NULL "
        "ORDER BY created_at LIMIT 1", (conn["household_id"],))
    adapter = get_adapter(conn["adapter"])
    config = conn["config"] or {}
    new_config, changed = adapter.prepare_config(config)
    if changed:
        execute("UPDATE source_connections SET config=%s WHERE id=%s",
                (json.dumps(new_config), connection_id))
        config = new_config
    events, cursor = adapter.fetch_history(config, conn["cursor"] or {})
    summary = ingest_events(str(owner["id"]), str(conn["provider_id"]), connection_id, events) \
        if events else {"inserted": 0}
    spec = adapter.library_prune_spec(config)
    if spec:
        summary["pruned"] = prune_connection_libraries(connection_id, spec[0], spec[1])
    # After a self-hosted (non-Trakt) sync, cross-check each touched series with
    # Trakt for episodes this source didn't know about, and re-attribute existing
    # Trakt events so they adopt the platform this real sync just established
    # (films included — the cross-sync only covers series).
    if conn["adapter"] != "trakt_api":
        enqueue_trakt_title_syncs(str(conn["household_id"]), str(owner["id"]),
                                  summary.get("series_title_ids"))
        if summary.get("inserted"):
            _enqueue_reattribute_trakt_all()
    elif summary.get("inserted"):
        # A bulk Trakt sync may have added events to already-enriched titles;
        # re-attribute them to their real streaming service.
        _enqueue_reattribute_trakt_all()
    execute("UPDATE source_connections SET cursor=%s, last_status=%s, last_sync_at=now() WHERE id=%s",
            (json.dumps(cursor), f"ok: +{summary.get('inserted', 0)}", connection_id))
    return summary


def _schedule_syncs():
    from app.db import query_all, execute
    conns = query_all(
        "SELECT id FROM source_connections WHERE enabled = true AND id IN "
        "(SELECT id FROM source_connections sc JOIN providers p ON p.id=sc.provider_id "
        " WHERE p.ingest_type='api')")
    for c in conns:
        execute(
            "INSERT INTO background_jobs (kind, payload) "
            "SELECT 'sync_connection', %s WHERE NOT EXISTS ("
            "  SELECT 1 FROM background_jobs WHERE kind='sync_connection' "
            "  AND payload->>'connection_id' = %s AND status IN ('pending','running'))",
            (json.dumps({"connection_id": str(c["id"])}), str(c["id"])),
        )


def _enqueue_reattribute_trakt_all():
    """Queue a one-shot backfill that moves existing Trakt events onto their real
    streaming service, deduped against any pending/running copy."""
    from app.db import execute
    execute(
        "INSERT INTO background_jobs (kind, payload) "
        "SELECT 'reattribute_trakt_all', '{}'::jsonb WHERE NOT EXISTS ("
        "  SELECT 1 FROM background_jobs WHERE kind='reattribute_trakt_all' "
        "  AND status IN ('pending','running'))")


def main():
    print("[worker] started", flush=True)
    try:
        _enqueue_reattribute_trakt_all()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    last_schedule = 0.0
    last_expire = 0.0
    while True:
        try:
            now = time.time()
            if now - last_schedule > SCHEDULE_INTERVAL:
                try:
                    _schedule_syncs()
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                last_schedule = now

            if now - last_expire > EXPIRE_INTERVAL:
                try:
                    from app.ingest import expire_stale_sessions
                    expire_stale_sessions(EXPIRE_AFTER_MINUTES)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                last_expire = now

            job = _claim_job()
            if not job:
                time.sleep(POLL_INTERVAL)
                continue
            try:
                result = _handle(job)
                _finish(job["id"], "done", result=result)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                _retry_or_fail(job, str(exc))
        except Exception:  # noqa: BLE001 — never let the loop die
            traceback.print_exc()
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
