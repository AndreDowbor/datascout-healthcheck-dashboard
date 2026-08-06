"""
run_checks.py — Runs IQA + Profile + Engage + Algolia checks sequentially.
Concierge checks run automatically via chat-monitor and don't need to be here.

Usage:
    python3 run_checks.py
"""

import subprocess
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import shutil
# Use the interpreter that's already running this script, not a fresh PATH
# lookup — cron/launchd run with a minimal PATH that doesn't include
# /opt/homebrew/bin, so shutil.which("python3.11") silently falls through to
# the system's old python3 (3.9), which is too old for the 1Password SDK's
# `X | None` type syntax and breaks every subprocess at import time.
PYTHON = sys.executable or shutil.which("python3.11") or shutil.which("python3")
BASE   = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

sys.path.insert(0, os.path.join(BASE, "common"))
from slack_alert import post_alert


def run(label: str, script: str, cwd: str) -> bool:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  [{now}] Starting: {label}")
    print(f"{'='*60}")

    result = subprocess.run(
        [PYTHON, script],
        cwd=cwd,
    )

    if result.returncode == 0:
        print(f"\n  ✅  {label} completed successfully.")
        return True
    else:
        print(f"\n  ❌  {label} failed (exit code {result.returncode}).")
        return False


def alert_production_failures(check_type: str) -> None:
    """Read latest Supabase results and alert on production failures."""
    try:
        from supabase import create_client
        url = os.getenv("DASHBOARD_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
        key = os.getenv("DASHBOARD_SUPABASE_KEY") or os.getenv("SUPABASE_KEY", "")
        if not url or not key:
            return
        sb = create_client(url, key)

        PRODUCTION_ENVS = {"aaae", "aboncle", "oasw", "cpanb"}

        if check_type == "IQA":
            res = sb.table("iqa_checks").select("environment,status,issues_count").order("checked_at", desc=True).limit(100).execute()
            seen = {}
            for row in res.data:
                env = row["environment"]
                if env not in seen:
                    seen[env] = row
            for env, row in seen.items():
                if env in PRODUCTION_ENVS and row.get("status", "").upper() in ("ISSUES", "DOWN"):
                    detail = f"{row.get('issues_count', 0)} issue(s)"
                    post_alert(env, "IQA", row["status"], detail)

        elif check_type == "Profile":
            res = sb.table("profile_checks").select("environment,status,error").order("checked_at", desc=True).limit(100).execute()
            seen = {}
            for row in res.data:
                env = row["environment"]
                if env not in seen:
                    seen[env] = row
            for env, row in seen.items():
                if env in PRODUCTION_ENVS and row.get("status", "").upper() == "FAIL":
                    post_alert(env, "Profile", "FAIL", row.get("error", "")[:80])

    except Exception as e:
        print(f"  [warn] Could not send Slack alerts: {e}")


if __name__ == "__main__":
    start = datetime.now()
    print(f"DataScout Health Checks — {start.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    results["IQA Healthcheck"] = run(
        label="IQA Healthcheck",
        script=os.path.join(BASE, "healthcheck", "iqa_healthcheck.py"),
        cwd=BASE,
    )
    alert_production_failures("IQA")

    PROFILE_DIR = os.path.join(BASE, "New_Profile_Tester")
    results["Profile Tester"] = run(
        label="Profile Tester",
        script=os.path.join(PROFILE_DIR, "imis_env_tester_with_1password.py"),
        cwd=PROFILE_DIR,
    )
    # Profile Tester pushes its own results to Supabase at the end of its
    # own run (see imis_env_tester_with_1password.py) — don't push again
    # here, that was double-inserting every row into profile_checks.
    alert_production_failures("Profile")

    results["Engage Healthcheck"] = run(
        label="Engage Healthcheck",
        script=os.path.join(BASE, "healthcheck", "engage_healthcheck.py"),
        cwd=BASE,
    )

    results["BO Healthcheck"] = run(
        label="BO Healthcheck",
        script=os.path.join(BASE, "healthcheck", "bo_healthcheck.py"),
        cwd=BASE,
    )

    results["Algolia Healthcheck"] = run(
        label="Algolia Healthcheck",
        script=os.path.join(BASE, "healthcheck", "algolia_healthcheck.py"),
        cwd=BASE,
    )

    elapsed = (datetime.now() - start).seconds
    print(f"\n{'='*60}")
    print(f"  All checks done in {elapsed}s")
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'}  {name}")
    print(f"{'='*60}\n")
