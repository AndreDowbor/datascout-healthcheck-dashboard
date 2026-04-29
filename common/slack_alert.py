"""
Slack alert poster for production environment failures.
Reads SLACK_WEBHOOK_URL from environment.
"""

import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta

PRODUCTION_ENVS = {"aaae", "aboncle", "oasw", "cpanb"}

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://datascout-healthcheck-dashboard.streamlit.app")


def _brt_now() -> str:
    brt = timezone(timedelta(hours=-3))
    return datetime.now(brt).strftime("%b %d %H:%M BRT")


def post_alert(env: str, check_type: str, status: str, detail: str = "") -> bool:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        return False

    label = "PRODUCTION" if env in PRODUCTION_ENVS else "STAGING"
    emoji = "🔴" if status.upper() in ("DOWN", "FAIL", "ISSUES") else "🟡"

    text = (
        f"{emoji} *datascout health alert*\n"
        f"*Environment:* {env} ({label})\n"
        f"*Check:* {check_type}\n"
        f"*Status:* {status}"
        + (f" — {detail}" if detail else "") +
        f"\n*Time:* {_brt_now()}\n"
        f"*Dashboard:* {DASHBOARD_URL}"
    )

    payload = json.dumps({"text": text}).encode()
    req = urllib.request.Request(webhook_url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def alert_if_production(env: str, check_type: str, status: str, detail: str = "") -> None:
    if env in PRODUCTION_ENVS:
        post_alert(env, check_type, status, detail)
