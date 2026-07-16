"""
bo_healthcheck.py — Checks DataScout Business Object presence across all environments.
Compares against the golden record (demo42) defined in healthcheck/golden_bos.json.
Pushes a summary to Supabase after each run.

Usage:
    python3 healthcheck/bo_healthcheck.py
"""

import asyncio
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from common.onepassword_manager import OnePasswordManager
from common.imis_client import IMISClient

GOLDEN_RECORD  = "demo42"
GOLDEN_BOS_FILE = REPO_ROOT / "healthcheck" / "golden_bos.json"
REQUEST_TIMEOUT = 15

# There's no per-name discovery API for Business Objects (unlike IQAs, which
# live in a browsable $/_DataScout folder). The full BO catalog — including
# stock iMIS objects — lives under this path instead; we filter to
# DataScout-named ones to find custom BOs that exist but aren't golden.
BO_ROOT = "$/Common/Business Objects"

CLIENT_IDS = [
    "demo83",
    "atsdemo89", "armdemo96", "imisdemo11", "imis36",
    "apimisdemo25", "imis87", "imis104", "demosales3", "demosales50", "demosales39", "demosales28",
    "atdemo2", "atdemo81", "demo14", "demo42", "bsidemo27", "demo86",
    "ensyncdemo13", "i8vdemo13", "ibcdemo80", "isgdemo14", "isgdemo106",
    "atsdemo90", "demosales33", "demosales44",
]

# BOs that behave as source panels — 403/400 without a member ID is expected,
# but 404 means genuinely missing.
SOURCE_PANELS = {"DataScout_Member_Properties"}

# BOs with known server-side issues in all environments — skip checking.
SKIP_BOS = {"Datascout_Max_Name_Log"}


def probe_bo(client: IMISClient, bo_name: str, timeout: int = REQUEST_TIMEOUT) -> str:
    """
    Returns: 'present' | 'missing' | 'broken' | 'error'
    """
    url = f"{client.base_url}/api/{bo_name}"
    headers = {"Authorization": client.token}
    try:
        resp = requests.get(url, headers=headers, params={"limit": 1}, timeout=timeout)
        if resp.status_code == 200:
            return "present"
        if resp.status_code == 404:
            return "missing"
        if bo_name in SOURCE_PANELS and resp.status_code in (400, 403):
            # Expected behaviour — BO exists but needs member context
            return "present"
        return "broken"
    except requests.exceptions.Timeout:
        return "error"
    except Exception:
        return "error"


def check_env(client: IMISClient, golden_bos: dict) -> dict:
    """
    Returns summary: { bo_name: status, ... }
    Status per BO: 'present' | 'missing' | 'broken' | 'skipped'
    """
    results = {}
    for bo_name in golden_bos:
        if bo_name in SKIP_BOS:
            results[bo_name] = "skipped"
            continue
        results[bo_name] = probe_bo(client, bo_name)
    return results


def discover_extra_bos(client: IMISClient, golden_bos: dict) -> list | None:
    """
    Return DataScout-named BOs that exist in this environment but aren't in
    the golden set. Returns None if discovery itself failed (not evidence
    there are no extras — just that we couldn't check).
    """
    golden_lower = {name.lower() for name in golden_bos}
    try:
        docs = client.list_documents_in_folder(BO_ROOT)
    except Exception:
        return None

    extra = []
    for doc in docs:
        if doc.get("Type") != "BUS":
            continue
        name = (doc.get("Path") or "").rsplit("/", 1)[-1]
        if name.lower().startswith("datascout") and name.lower() not in golden_lower:
            extra.append(name)
    return sorted(extra)


async def main():
    with open(GOLDEN_BOS_FILE) as f:
        golden = json.load(f)
    golden_bos = golden["business_objects"]

    checkable_bos = [bo for bo in golden_bos if bo not in SKIP_BOS]
    print(f"Golden record: {GOLDEN_RECORD}")
    print(f"BOs to check: {len(checkable_bos)} ({len(SKIP_BOS)} skipped)\n")

    op = OnePasswordManager()

    print("Fetching credentials from 1Password...")
    environment_credentials = {}
    for client_id in CLIENT_IDS:
        try:
            secrets = await op.get_flattened_client_item(client_id)
            base_url = secrets.get("imis_base_url")
            username = secrets.get("username")
            password = secrets.get("password")
            if not all([base_url, username, password]):
                continue
            environment_credentials[client_id] = {
                "imis_base_url": base_url,
                "username": username,
                "password": password,
            }
        except Exception:
            pass

    print(f"Loaded {len(environment_credentials)} environments.\n")

    all_results = []
    checked_at = dt.datetime.now(dt.timezone.utc).isoformat()

    for client_id, creds in environment_credentials.items():
        print(f"\n── {client_id} ──")
        try:
            imis = IMISClient(creds["imis_base_url"], creds["username"], creds["password"])
        except Exception as e:
            print(f"  ❌ Login failed: {e}")
            all_results.append({
                "environment": client_id,
                "status": "DOWN",
                "issues_count": len(checkable_bos),
                "details": {"error": str(e)[:120], "missing": [], "broken": [], "extra": []},
                "checked_at": checked_at,
            })
            continue

        bo_results = check_env(imis, golden_bos)
        extra_bos  = discover_extra_bos(imis, golden_bos)

        missing = [bo for bo, s in bo_results.items() if s == "missing"]
        broken  = [bo for bo, s in bo_results.items() if s == "broken"]
        errored = [bo for bo, s in bo_results.items() if s == "error"]
        issues_count = len(missing) + len(broken) + len(errored) + len(extra_bos or [])

        if issues_count == 0:
            status = "OK"
        else:
            status = "ISSUES"

        icons = {"present": "✅", "missing": "❌", "broken": "⚠️ ", "skipped": "–", "error": "⏱️ "}
        for bo, s in bo_results.items():
            print(f"  {icons.get(s, '?')}  {bo}")

        if extra_bos is None:
            print("  ⚠️  Extra-BO discovery failed — skipping (not evidence there are none).")
        else:
            for name in extra_bos:
                print(f"  🟣  {name} (extra, not in golden)")

        all_results.append({
            "environment": client_id,
            "status": status,
            "issues_count": issues_count,
            "details": {"missing": missing, "broken": broken, "errored": errored, "extra": extra_bos or []},
            "checked_at": checked_at,
        })

    # Push to Supabase
    sb_url = os.getenv("DASHBOARD_SUPABASE_URL", "")
    sb_key = os.getenv("DASHBOARD_SUPABASE_KEY", "")
    if sb_url and sb_key:
        try:
            from supabase import create_client
            supabase = create_client(sb_url, sb_key)
            supabase.table("bo_checks").insert(all_results).execute()
            print(f"\n  → Pushed {len(all_results)} BO results to Supabase.")
        except Exception as exc:
            print(f"\n  [warn] Supabase push failed: {exc}")
    else:
        print("\n  [warn] DASHBOARD_SUPABASE_URL/KEY not set — skipping Supabase push.")

    ok     = sum(1 for r in all_results if r["status"] == "OK")
    issues = sum(1 for r in all_results if r["status"] == "ISSUES")
    down   = sum(1 for r in all_results if r["status"] == "DOWN")
    print(f"\n✅ {ok} OK  ⚠️  {issues} with issues  ❌ {down} down")


if __name__ == "__main__":
    asyncio.run(main())
