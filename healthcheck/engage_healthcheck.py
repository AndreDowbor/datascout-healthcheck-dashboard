"""
engage_healthcheck.py — Engage dashboard healthcheck across all production orgs.
Logs into engage.app.datascout.ai, selects each org, confirms the dashboard loads,
navigates to Segments → All Members, and captures console errors throughout.
Pushes results to Supabase (engage_checks table).

Usage:
    python3 engage_healthcheck.py
"""

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ── Load credentials ──────────────────────────────────────────────────────────
REPO_ROOT    = Path(__file__).resolve().parents[1]
ENGAGE_ROOT  = Path("/Users/andredowbor/Projects/work/datascout/engage-automation")

load_dotenv(REPO_ROOT / ".env")
load_dotenv(ENGAGE_ROOT / ".env", override=False)

# ── Config ────────────────────────────────────────────────────────────────────
EMAIL       = os.getenv("ENGAGE_EMAIL")
PASSWORD    = os.getenv("ENGAGE_PASSWORD")
ENVIRONMENT = os.getenv("ENGAGE_ENV", "production").strip().lower()

if ENVIRONMENT == "staging":
    BASE_URL = os.getenv("ENGAGE_STAGING_URL", "https://engage.staging.app.datascout.ai")
    ORGS_RAW = os.getenv("ENGAGE_STAGING_TARGET_ORGS", "")
else:
    BASE_URL = os.getenv("ENGAGE_PROD_URL", "https://engage.app.datascout.ai")
    ORGS_RAW = os.getenv("ENGAGE_PROD_TARGET_ORGS", "")

TARGET_ORGS = [o.strip() for o in ORGS_RAW.split(",") if o.strip()]

SLOW_THRESHOLD_S      = 20.0
DASHBOARD_TIMEOUT_MS  = 20000
ORG_PICKER_TIMEOUT_MS = 30000
LOGIN_TIMEOUT_MS      = 30000
SEGMENTS_TIMEOUT_MS   = 15000
ALL_MEMBERS_TIMEOUT_MS = 15000
GRID_TIMEOUT_MS       = 20000

DASHBOARD_SIGNALS = ["Insights Dashboard", "Dashboard"]

# Console message types to treat as errors
CONSOLE_ERROR_TYPES = {"error"}

# Noise patterns to filter out from console errors (AG Grid deprecation warnings etc.)
NOISE_PATTERNS = [
    "AG Grid:",
    "Download the React DevTools",
    "[DEBUG]",
    "🔍",
    "🔄",
    "✅",
    "👤",
    "🔐",
    "🔑",
    "🌐",
    "🧹",
    "📊",
]


def is_noise(msg: str) -> bool:
    return any(p in msg for p in NOISE_PATTERNS)


# ── Supabase ──────────────────────────────────────────────────────────────────
def _get_supabase():
    try:
        from supabase import create_client
        url = os.getenv("DASHBOARD_SUPABASE_URL", "")
        key = os.getenv("DASHBOARD_SUPABASE_KEY", "")
        if url and key:
            return create_client(url, key)
    except Exception as e:
        print(f"  [warn] Supabase init failed: {e}")
    return None


def push_results(results: list[dict]):
    sb = _get_supabase()
    if not sb:
        print("  [warn] Supabase not configured, skipping push.")
        return
    ts = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "org":                  r["org"],
            "status":               r["status"],
            "load_time_seconds":    r.get("load_time_seconds"),
            "dashboard_ok":         r.get("dashboard_ok", False),
            "error_reason":         r.get("error_reason"),
            "console_error_count":  r.get("console_error_count", 0),
            "page_error_count":     r.get("page_error_count", 0),
            "request_failure_count": r.get("request_failure_count", 0),
            "errors_summary":       r.get("errors_summary"),
            "checked_at":           ts,
        }
        for r in results
    ]
    try:
        sb.table("engage_checks").insert(rows).execute()
        print(f"  → Pushed {len(rows)} Engage results to Supabase.")
    except Exception as e:
        print(f"  [warn] Supabase push failed: {e}")


# ── Playwright helpers ────────────────────────────────────────────────────────
def classify_status(load_time: float, dashboard_ok: bool,
                    console_errors: int, page_errors: int, request_failures: int) -> str:
    if not dashboard_ok:
        return "DOWN"
    if page_errors > 0 or console_errors > 0:
        return "PARTIAL"
    if request_failures > 0:
        return "DEGRADED"
    if load_time >= SLOW_THRESHOLD_S:
        return "SLOW"
    return "OK"


def attach_observers(page) -> tuple[list, list, list]:
    console_messages: list[dict[str, Any]] = []
    page_errors:      list[dict[str, Any]] = []
    request_failures: list[dict[str, Any]] = []

    def on_console(msg):
        try:
            console_messages.append({"type": msg.type, "text": msg.text})
        except Exception:
            pass

    def on_page_error(err):
        try:
            page_errors.append({"message": str(err)})
        except Exception:
            pass

    def on_request_failed(req):
        try:
            failure = req.failure
            request_failures.append({
                "url":   req.url,
                "error": failure.get("errorText") if failure else "unknown",
            })
        except Exception:
            pass

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)

    return console_messages, page_errors, request_failures


def build_errors_summary(console_messages: list, page_errors: list, request_failures: list) -> str | None:
    parts = []

    console_errors = [
        m["text"] for m in console_messages
        if m.get("type") in CONSOLE_ERROR_TYPES and not is_noise(m.get("text", ""))
    ]
    if console_errors:
        unique = list(dict.fromkeys(console_errors))[:3]
        parts.append("Console: " + " | ".join(t[:80] for t in unique))

    if page_errors:
        unique = list(dict.fromkeys(e["message"] for e in page_errors))[:2]
        parts.append("JS: " + " | ".join(t[:80] for t in unique))

    if request_failures:
        unique = list(dict.fromkeys(f["error"] for f in request_failures))[:2]
        parts.append("Requests: " + " | ".join(t[:80] for t in unique))

    return "; ".join(parts) if parts else None


def login(page):
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    if "/login" in page.url:
        page.wait_for_selector("#email", timeout=LOGIN_TIMEOUT_MS)
        page.fill("#email", EMAIL)
        page.fill("#password", PASSWORD)
        page.click("button[type='submit']")
        page.wait_for_url(lambda url: "/login" not in url, timeout=LOGIN_TIMEOUT_MS)
    page.wait_for_load_state("networkidle")


def select_org(page, org_name: str):
    page.wait_for_selector("button span", timeout=ORG_PICKER_TIMEOUT_MS)
    btn = page.get_by_role("button", name=org_name, exact=True).first
    btn.scroll_into_view_if_needed()
    btn.click()
    page.wait_for_load_state("networkidle")


def wait_for_dashboard(page) -> bool:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    for text in DASHBOARD_SIGNALS:
        try:
            page.wait_for_selector(f"text={text}", timeout=DASHBOARD_TIMEOUT_MS)
            return True
        except PlaywrightTimeoutError:
            continue
    return False


def navigate_to_all_members(page) -> bool:
    try:
        page.get_by_role("button", name="Segments", exact=True).first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        page.get_by_role("link", name="All Members", exact=True).first.click()
        page.wait_for_load_state("networkidle")
        # Wait for AG Grid or table to appear
        page.wait_for_selector("div[role='gridcell'], table tbody tr", timeout=GRID_TIMEOUT_MS)
        return True
    except Exception:
        return False


def check_org(browser, org_name: str) -> dict:
    result: dict[str, Any] = {
        "org":                  org_name,
        "status":               "UNKNOWN",
        "load_time_seconds":    None,
        "dashboard_ok":         False,
        "error_reason":         None,
        "console_error_count":  0,
        "page_error_count":     0,
        "request_failure_count": 0,
        "errors_summary":       None,
    }

    context = browser.new_context()
    page    = context.new_page()
    console_messages, page_errors, request_failures = attach_observers(page)
    start   = time.time()

    try:
        login(page)
        select_org(page, org_name)
        dashboard_ok = wait_for_dashboard(page)
        result["dashboard_ok"] = dashboard_ok

        if dashboard_ok:
            navigate_to_all_members(page)

        load_time = round(time.time() - start, 2)
        result["load_time_seconds"] = load_time

        console_err_count = sum(
            1 for m in console_messages
            if m.get("type") in CONSOLE_ERROR_TYPES and not is_noise(m.get("text", ""))
        )
        result["console_error_count"]   = console_err_count
        result["page_error_count"]      = len(page_errors)
        result["request_failure_count"] = len(request_failures)
        result["errors_summary"]        = build_errors_summary(console_messages, page_errors, request_failures)
        result["status"] = classify_status(
            load_time, dashboard_ok, console_err_count, len(page_errors), len(request_failures)
        )

    except PlaywrightTimeoutError as e:
        result["load_time_seconds"] = round(time.time() - start, 2)
        result["status"]       = "DOWN"
        result["error_reason"] = f"Timeout: {str(e)[:150]}"
    except Exception as e:
        result["load_time_seconds"] = round(time.time() - start, 2)
        result["status"]       = "DOWN"
        result["error_reason"] = f"Error: {str(e)[:150]}"
    finally:
        context.close()

    return result


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not EMAIL or not PASSWORD:
        print("[error] ENGAGE_EMAIL and ENGAGE_PASSWORD must be set.", file=sys.stderr)
        sys.exit(1)
    if not TARGET_ORGS:
        print("[error] ENGAGE_PROD_TARGET_ORGS is empty.", file=sys.stderr)
        sys.exit(1)

    print(f"\nEngage Healthcheck — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL : {BASE_URL}")
    print(f"Orgs     : {len(TARGET_ORGS)}\n")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for org in TARGET_ORGS:
            print(f"  Checking: {org} ...", end=" ", flush=True)
            r = check_org(browser, org)
            results.append(r)
            icon = "✅" if r["status"] == "OK" else ("⚠️ " if r["status"] in ("SLOW", "DEGRADED", "PARTIAL") else "❌")
            detail = f"{r['status']} ({r['load_time_seconds']}s)"
            if r.get("console_error_count"):
                detail += f" | {r['console_error_count']} console err"
            if r.get("page_error_count"):
                detail += f" | {r['page_error_count']} JS err"
            print(f"{icon} {detail}")
            if r.get("errors_summary"):
                print(f"    ↳ {r['errors_summary']}")
        browser.close()

    counts = {s: sum(1 for r in results if r["status"] == s) for s in ["OK", "SLOW", "PARTIAL", "DEGRADED", "DOWN"]}
    print(f"\n  Summary: " + "  ".join(f"{k}={v}" for k, v in counts.items() if v > 0))
    push_results(results)


if __name__ == "__main__":
    main()
