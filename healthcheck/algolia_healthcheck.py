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
    "demo83",
    "aaae", "atsdemo89", "aboncle", "armdemo96", "imisdemo11", "imis36",
    "apimisdemo25", "imis87", "imis104", "demosales3", "demosales50", "demosales39",
    "atdemo2", "atdemo81", "demo42", "bsidemo27", "demo86",
    "ensyncdemo13", "i8vdemo13", "ibcdemo80", "isgdemo14", "isgdemo106",
    "oasw", "cpanb",
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

    try:
        resp = requests.get(
            f"https://{host}/1/indexes",
            headers={
                "X-Algolia-Application-Id": app_id,
                "X-Algolia-API-Key": search_key,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return {"status": "OK", "error": None}
        elif resp.status_code in (401, 403):
            return {"status": "AUTH_ERROR", "error": f"HTTP {resp.status_code} — key may be rotated"}
        else:
            return {"status": "ERROR", "error": f"HTTP {resp.status_code}"}
    except requests.exceptions.RequestException as e:
        return {"status": "ERROR", "error": str(e)[:120]}


async def main():
    print("Fetching Algolia credentials from 1Password...")
    op = OnePasswordManager()

    results = []
    checked_at = datetime.now(timezone.utc).isoformat()

    for client_id in CLIENT_IDS:
        try:
            creds = await op.get_flattened_client_item(client_id)
            app_id = creds.get("algolia_app_id", "")
            search_key = creds.get("algolia_search_key", "") or creds.get("algolia_write_key", "")
        except Exception as e:
            print(f"  {client_id}: SKIP — 1Password error: {e}")
            results.append({"environment": client_id, "status": "SKIP", "app_id": None, "checked_at": checked_at, "error": str(e)[:120]})
            continue

        result = check_algolia_app(app_id, search_key)
        icon = {"OK": "✅", "DOWN": "❌", "AUTH_ERROR": "⚠️ ", "SKIP": "–", "NO_KEY": "⚠️ ", "ERROR": "❌"}.get(result["status"], "?")
        print(f"  {icon}  {client_id:<20} {app_id or '(none)':<16} {result['status']}" + (f" — {result['error']}" if result.get("error") else ""))

        results.append({
            "environment": client_id,
            "status": result["status"],
            "app_id": app_id or None,
            "checked_at": checked_at,
            "error": result.get("error"),
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
    print(f"\n✅ {ok} OK  ❌ {down} issues  – {len(results) - ok - down} skipped/no-key")


if __name__ == "__main__":
    asyncio.run(main())
