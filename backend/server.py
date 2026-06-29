"""WatchVault MCP server — a minimal streamable-HTTP JSON-RPC bridge.

Exposes household watch data to AI assistants. Authenticates with a per-user
WatchVault API token (Bearer wvapi_…) and gates each tool on permission keys
(mcp.use + mcp.tool.<name>). Run:

    python server.py --http --host 0.0.0.0 --port 7211
"""
from __future__ import annotations

import argparse

from flask import Flask, jsonify, request

from app.db import query_all, query_one
from app.util import hash_secret

app = Flask(__name__)
PROTOCOL_VERSION = "2024-11-05"

EFF_SECONDS = "COALESCE(we.duration_seconds, t.runtime_minutes * 60, 0)"

TOOLS = [
    {
        "name": "search",
        "permission": "mcp.tool.search",
        "description": "Search watched titles by name, genre, actor, platform or year.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search"},
                "genre": {"type": "string"},
                "actor": {"type": "string"},
                "platform": {"type": "string"},
                "year": {"type": "integer"},
            },
        },
    },
    {
        "name": "stats",
        "permission": "mcp.tool.stats",
        "description": "Household watch statistics: totals, hours, and top platforms.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ── Auth ───────────────────────────────────────────────────────────────────

def resolve_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    if not token.startswith("wvapi_"):
        return None
    prefix = token[: token.find("_") + 9]
    for c in query_all("SELECT * FROM api_clients WHERE token_prefix = %s AND revoked_at IS NULL",
                       (prefix,)):
        if hash_secret(token, c["salt"]) == c["token_hash"]:
            user = query_one("SELECT * FROM users WHERE id = %s AND deleted_at IS NULL",
                             (c["user_id"],))
            if not user:
                return None
            perms = query_all(
                "SELECT DISTINCT rp.permission_key AS key FROM user_roles ur "
                "JOIN role_permissions rp ON rp.role_id = ur.role_id WHERE ur.user_id = %s",
                (user["id"],))
            user["permissions"] = {p["key"] for p in perms}
            if user["is_admin"]:
                user["permissions"].add("*")
            return user
    return None


def has_perm(user, key):
    p = user.get("permissions", set())
    return "*" in p or key in p


def household_ids(user):
    rows = query_all("SELECT id FROM users WHERE household_id = %s AND deleted_at IS NULL",
                     (user["household_id"],))
    return [str(r["id"]) for r in rows]


# ── Tool implementations ───────────────────────────────────────────────────

def tool_search(user, args):
    ids = household_ids(user)
    q = (args.get("query") or "").strip()
    where = ["we.user_id = ANY(%s::uuid[])", "we.deleted_at IS NULL"]
    params = [ids]
    if q:
        where.append("t.title ILIKE %s")
        params.append(f"%{q}%")
    for field, col in (("genre", "g.name"), ("actor", "pe.name")):
        if args.get(field):
            if field == "genre":
                where.append("EXISTS (SELECT 1 FROM title_genres tg JOIN genres g ON g.id=tg.genre_id "
                             "WHERE tg.title_id=t.id AND g.name ILIKE %s)")
            else:
                where.append("EXISTS (SELECT 1 FROM title_people tp JOIN people pe ON pe.id=tp.person_id "
                             "WHERE tp.title_id=t.id AND pe.name ILIKE %s)")
            params.append(f"%{args[field]}%")
    if args.get("year"):
        where.append("t.year = %s")
        params.append(int(args["year"]))
    if args.get("platform"):
        where.append("we.provider_id IN (SELECT id FROM providers WHERE key=%s OR name ILIKE %s)")
        params += [args["platform"], f"%{args['platform']}%"]
    rows = query_all(
        f"SELECT t.title, t.kind, t.year, count(*) AS events "
        f"FROM watch_events we JOIN titles t ON t.id=we.title_id "
        f"WHERE {' AND '.join(where)} GROUP BY t.id ORDER BY events DESC LIMIT 40",
        params,
    )
    if not rows:
        return "No matching titles found."
    return "\n".join(f"- {r['title']} ({r['year'] or '?'}, {r['kind']}) — {r['events']} plays"
                     for r in rows)


def tool_stats(user, args):
    ids = household_ids(user)
    t = query_one(
        f"SELECT count(*) AS events, count(*) FILTER (WHERE we.item_kind='movie') AS movies, "
        f"count(*) FILTER (WHERE we.item_kind='episode') AS episodes, "
        f"count(DISTINCT we.title_id) AS titles, COALESCE(sum({EFF_SECONDS}),0) AS seconds "
        f"FROM watch_events we LEFT JOIN titles t ON t.id=we.title_id "
        f"WHERE we.user_id = ANY(%s::uuid[]) AND we.deleted_at IS NULL",
        (ids,),
    )
    plat = query_all(
        "SELECT p.name, sum(a.events_count) AS events FROM watch_daily_agg a "
        "JOIN providers p ON p.id=a.provider_id WHERE a.user_id = ANY(%s::uuid[]) "
        "GROUP BY p.name ORDER BY events DESC LIMIT 5", (ids,))
    lines = [
        f"Household '{user.get('household_id')}' watch stats:",
        f"- {t['events']} events ({t['movies']} movies, {t['episodes']} episodes)",
        f"- {t['titles']} distinct titles",
        f"- {round((t['seconds'] or 0)/3600,1)} hours watched",
        "Top platforms: " + ", ".join(f"{p['name']} ({p['events']})" for p in plat),
    ]
    return "\n".join(lines)


TOOL_FUNCS = {"search": tool_search, "stats": tool_stats}


# ── JSON-RPC endpoint ──────────────────────────────────────────────────────

def rpc_result(req_id, result):
    return jsonify({"jsonrpc": "2.0", "id": req_id, "result": result})


def rpc_error(req_id, code, message):
    return jsonify({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


@app.post("/mcp")
@app.post("/")
def mcp():
    body = request.get_json(force=True, silent=True) or {}
    method = body.get("method")
    req_id = body.get("id")
    params = body.get("params") or {}

    if method == "initialize":
        return rpc_result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "watchvault", "version": "1.0.0"},
        })
    if method in ("notifications/initialized", "ping"):
        return ("", 204) if req_id is None else rpc_result(req_id, {})

    user = resolve_user()
    if not user:
        return rpc_error(req_id, -32001, "unauthorized: provide a Bearer wvapi_ token")
    if not has_perm(user, "mcp.use"):
        return rpc_error(req_id, -32002, "forbidden: mcp.use required")

    if method == "tools/list":
        tools = [{"name": t["name"], "description": t["description"],
                  "inputSchema": t["inputSchema"]}
                 for t in TOOLS if has_perm(user, t["permission"])]
        return rpc_result(req_id, {"tools": tools})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = next((t for t in TOOLS if t["name"] == name), None)
        if not tool:
            return rpc_error(req_id, -32601, f"unknown tool: {name}")
        if not has_perm(user, tool["permission"]):
            return rpc_error(req_id, -32002, f"forbidden: {tool['permission']} required")
        try:
            text = TOOL_FUNCS[name](user, args)
        except Exception as exc:  # noqa: BLE001
            return rpc_error(req_id, -32603, f"tool error: {exc}")
        return rpc_result(req_id, {"content": [{"type": "text", "text": text}]})

    return rpc_error(req_id, -32601, f"unknown method: {method}")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7211)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
