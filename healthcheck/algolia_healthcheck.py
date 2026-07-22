"""
algolia_healthcheck.py — Checks Algolia app health per Datascout client.
Fetches app_id + search_key from 1Password, then hits the Algolia API.
"""

import asyncio
import sys
import os
import socket
import requests
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "common"))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

from onepassword_manager import OnePasswordManager

CLIENT_IDS = [
    # Clients
    "aaae", "abca", "aboncle", "cpanb", "cpsu", "livediff", "nteu", "oasw", "trail",
    # BSI Demo
    "bsidemo27",
    # Datascout Partner demos
    "armdemo96", "atdemo2", "atdemo81", "atsdemo89", "atsdemo90",
    "demo14", "ensyncdemo13", "i8vdemo13", "ibcdemo80", "imis104", "imis87",
    "isgdemo106", "isgdemo14", "demosales33", "demosales44",
    # ASI demos
    "apimisdemo25", "demosales3", "demosales28", "demosales39", "demosales50",
    "imis36", "imisdemo11",
    # Internal Datascout
    "demo42", "demo83", "demo86",
    # Union Pilot
    "psansw",
]


def check_algolia_app(app_id: str, search_key: str) -> dict:
    if not app_id:
        return {"status": "SKIP", "error": "no app_id in 1Password"}

    host = f"{app_id}-dsn.algolia.net"
    try:
        socket.getaddrinfo(host, 443)
    except socket.gaierror:
        return {"status": "DOWN", "error": "DNS resolution failed — app may be archived"}

    if not search_key:
        return {"status": "NO_KEY", "error": "app exists but no search key in 1Password"}

    headers = {
        "X-Algolia-Application-Id": app_id,
        "X-Algolia-API-Key": search_key,
    }

    try:
        # List indices to confirm app is reachable
        resp = requests.get(
            f"https://{host}/1/indexes",
            headers=headers,
            timeout=10,
        )
        if resp.status_code in (401, 403):
            return {"status": "AUTH_ERROR", "error": f"HTTP {resp.status_code} — key may be rotated"}
        if resp.status_code != 200:
            return {"status": "ERROR", "error": f"HTTP {resp.status_code}"}

        # Keep-alive: run a real search on the first available index so Algolia
        # counts this as activity and does not archive/pause the app due to
        # inactivity. We verify the search itself actually succeeded — firing
        # it and ignoring the response would silently defeat the purpose.
        indices = resp.json().get("items", [])
        if not indices:
            return {"status": "OK", "error": None, "search_performed": False,
                     "search_note": "app has 0 indices — nothing to search, no keep-alive signal sent"}

        index_name = indices[0].get("name", "")
        try:
            search_resp = requests.post(
                f"https://{host}/1/indexes/{index_name}/query",
                headers={**headers, "Content-Type": "application/json"},
                json={"query": "", "hitsPerPage": 1},
                timeout=10,
            )
        except requests.exceptions.RequestException as e:
            return {"status": "OK", "error": None, "search_performed": False,
                     "search_note": f"search request failed: {str(e)[:100]}"}

        if search_resp.status_code != 200:
            return {"status": "OK", "error": None, "search_performed": False,
                     "search_note": f"search returned HTTP {search_resp.status_code} — keep-alive NOT confirmed"}

        return {"status": "OK", "error": None, "search_performed": True,
                 "search_note": f"real search OK on index '{index_name}'"}

    except requests.exceptions.RequestException as e:
        return {"status": "ERROR", "error": str(e)[:120]}


async def main():
    print("Fetching Algolia credentials from 1Password...")
    op = OnePasswordManager()

    results = []
    search_flags = []
    checked_at = datetime.now(timezone.utc).isoformat()

    for client_id in CLIENT_IDS:
        try:
            creds = await op.get_flattened_client_item(client_id)
            app_id = creds.get("algolia_app_id", "")
            search_key = creds.get("algolia_search_key", "") or creds.get("algolia_write_key", "")
        except Exception as e:
            print(f"  {client_id}: SKIP — 1Password error: {e}")
            results.append({"environment": client_id, "status": "SKIP", "app_id": None, "checked_at": checked_at, "error": str(e)[:120]})
            search_flags.append(None)
            continue

        result = check_algolia_app(app_id, search_key)
        search_performed = result.get("search_performed")
        search_flags.append(search_performed)
        icon = {"OK": "✅", "DOWN": "❌", "AUTH_ERROR": "⚠️ ", "SKIP": "–", "NO_KEY": "⚠️ ", "ERROR": "❌"}.get(result["status"], "?")
        if result["status"] == "OK" and search_performed is False:
            icon = "⚠️ "  # connectivity fine, but the keep-alive search itself is unconfirmed
        line = f"  {icon}  {client_id:<20} {app_id or '(none)':<16} {result['status']}"
        if result.get("error"):
            line += f" — {result['error']}"
        elif result.get("search_note"):
            line += f" — {result['search_note']}"
        print(line)

        # NOTE: search_performed/search_note aren't pushed to Supabase — the
        # algolia_checks table schema isn't known to include them, and a
        # rejected insert would silently lose the whole batch. When status is
        # OK but the keep-alive search wasn't confirmed, we fold that into
        # the "error" column so it's still visible on the dashboard.
        results.append({
            "environment": client_id,
            "status": result["status"],
            "app_id": app_id or None,
            "checked_at": checked_at,
            "error": result.get("error") or (None if search_performed else result.get("search_note")),
        })

    # Push to Supabase
    try:
        from supabase import create_client
        url = os.getenv("DASHBOARD_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
        key = os.getenv("DASHBOARD_SUPABASE_KEY") or os.getenv("SUPABASE_KEY", "")
        if url and key:
            sb = create_client(url, key)
            sb.table("algolia_checks").insert(results).execute()
            print(f"\n  → Pushed {len(results)} Algolia results to Supabase.")
    except Exception as e:
        print(f"\n  [warn] Supabase push failed: {e}")

    ok = sum(1 for r in results if r["status"] == "OK")
    down = sum(1 for r in results if r["status"] in ("DOWN", "AUTH_ERROR", "ERROR"))
    searched = sum(1 for r in search_flags if r)
    not_searched = sum(1 for r in search_flags if r is False)
    print(f"\n✅ {ok} OK  ❌ {down} issues  – {len(results) - ok - down} skipped/no-key")
    print(f"🔎 Keep-alive search confirmed on {searched} apps  ⚠️  {not_searched} OK-but-unconfirmed (empty index / search failed)")


if __name__ == "__main__":
    asyncio.run(main())
