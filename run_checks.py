"""
run_checks.py — Runs IQA + Profile checks sequentially and pushes results to Supabase.
Concierge checks run automatically via chat-monitor and don't need to be here.

Usage:
    python3 run_checks.py
"""

import subprocess
import sys
import os
from datetime import datetime

PYTHON = sys.executable
BASE   = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


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


if __name__ == "__main__":
    start = datetime.now()
    print(f"DataScout Health Checks — {start.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    results["IQA Healthcheck"] = run(
        label="IQA Healthcheck",
        script=os.path.join(BASE, "healthcheck", "iqa_healthcheck.py"),
        cwd=BASE,
    )

    results["Profile Tester"] = run(
        label="Profile Tester",
        script="/Users/andredowbor/Repos/chat-monitor/New_Profile_Tester/imis_env_tester_with_1password.py",
        cwd="/Users/andredowbor/Repos/chat-monitor/New_Profile_Tester",
    )

    elapsed = (datetime.now() - start).seconds
    print(f"\n{'='*60}")
    print(f"  All checks done in {elapsed}s")
    for name, ok in results.items():
        print(f"  {'✅' if ok else '❌'}  {name}")
    print(f"{'='*60}\n")
