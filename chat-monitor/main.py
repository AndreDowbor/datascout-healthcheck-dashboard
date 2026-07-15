"""
main.py — Entry point for Concierge Chat Functional Monitor.

Usage:
    python main.py

Setup (first time only):
    pip install -r requirements.txt
    playwright install chromium
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from playwright.async_api import async_playwright
from supabase import create_client

from logger import setup_logger, StructuredLogger
from monitor import check_url
from scheduler import run_scheduler
from imis_monitor import check_url_imis_login

load_dotenv(Path(__file__).parent / ".env")

def _get_supabase():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if url and key:
        return create_client(url, key)
    return None


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

# Defaults applied when optional config keys are missing
CONFIG_DEFAULTS = {
    "check_times_per_day": 2,
    "schedule_anchor": "00:00",
    "playwright_headless": True,
    "log_max_bytes": 5 * 1024 * 1024,
    "log_backup_count": 5,
    "test_message": "Hello, this is an automated health check. Please respond with OK.",
}

URL_DEFAULTS = {
    "http_timeout": 10,
    "widget_timeout": 30,
    "chat_timeout": 60,
    "response_container_selector": None,
}


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def load_and_validate_config(path: str) -> dict[str, Any]:
    """
    Load config.json, apply defaults, and validate required fields.
    Exits with code 1 on any validation error.
    """
    if not os.path.exists(path):
        print(f"[error] config.json not found at: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as exc:
            print(f"[error] Invalid JSON in config: {exc}", file=sys.stderr)
            sys.exit(1)

    config = {**CONFIG_DEFAULTS, **raw}

    # Validate check_times_per_day
    ctpd = config.get("check_times_per_day")
    if not isinstance(ctpd, int) or ctpd < 1:
        print(
            "[error] check_times_per_day must be an integer >= 1", file=sys.stderr
        )
        sys.exit(1)

    # Validate schedule_anchor format
    anchor = config.get("schedule_anchor", "00:00")
    try:
        h, m = anchor.split(":")
        assert 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except Exception:
        print(
            f"[error] schedule_anchor must be HH:MM (got: {anchor!r})",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate urls list
    urls = config.get("urls")
    if not isinstance(urls, list) or len(urls) == 0:
        print("[error] urls must be a non-empty list", file=sys.stderr)
        sys.exit(1)

    for i, entry in enumerate(urls):
        if not isinstance(entry, dict):
            print(f"[error] urls[{i}] must be an object", file=sys.stderr)
            sys.exit(1)
        if not entry.get("name") or not entry.get("url"):
            print(
                f"[error] urls[{i}] must have 'name' and 'url' fields",
                file=sys.stderr,
            )
            sys.exit(1)
        # Apply per-URL defaults
        for k, v in URL_DEFAULTS.items():
            entry.setdefault(k, v)

    return config


# ---------------------------------------------------------------------------
# Check cycle
# ---------------------------------------------------------------------------


def _notify(title: str, message: str) -> None:
    """Send a macOS notification (best-effort, silent on failure)."""
    try:
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(["osascript", "-e", script], check=False, timeout=5)
    except Exception:
        pass


async def run_checks(config: dict[str, Any], logger: StructuredLogger) -> None:
    """Run one full check cycle across all URLs."""
    headless = config.get("playwright_headless", True)
    timestamp = datetime.now(timezone.utc).isoformat()

    counts: dict[str, int] = {"UP": 0, "DEGRADED": 0, "DOWN": 0}
    failures: list[str] = []
    all_results: list[dict] = []

    # Initialize 1Password manager once if any imis_member entries exist
    op_manager = None
    if any(e.get("type") == "imis_member" for e in config["urls"]):
        try:
            from imis_monitor import OnePasswordManager
            op_manager = OnePasswordManager()
        except Exception as exc:
            print(f"[warn] Could not initialize 1Password manager: {exc}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        try:
            for entry in config["urls"]:
                if entry.get("type") == "imis_member":
                    if op_manager is None:
                        result = {
                            "name": entry["name"],
                            "url": entry["url"],
                            "status": "DOWN",
                            "error": "1Password manager unavailable",
                        }
                    else:
                        result = await check_url_imis_login(
                            entry=entry,
                            global_config=config,
                            browser=browser,
                            op_manager=op_manager,
                        )
                else:
                    result = await check_url(
                        entry=entry,
                        global_config=config,
                        browser=browser,
                    )
                _print_result(result)
                logger.structured({**result, "timestamp": timestamp})
                all_results.append(result)

                status = result.get("status", "DOWN")
                if status == "UP":
                    counts["UP"] += 1
                elif "DEGRADED" in status:
                    counts["DEGRADED"] += 1
                    failures.append(f"{result['name']}: {status}")
                else:
                    counts["DOWN"] += 1
                    failures.append(f"{result['name']}: DOWN")
        finally:
            await browser.close()

    total = sum(counts.values())
    logger.structured({
        "event": "cycle_complete",
        "total": total,
        "up": counts["UP"],
        "degraded": counts["DEGRADED"],
        "down": counts["DOWN"],
        "timestamp": timestamp,
    })
    print(
        f"\n── Cycle complete: {counts['UP']}/{total} UP"
        + (f", {counts['DEGRADED']} DEGRADED" if counts["DEGRADED"] else "")
        + (f", {counts['DOWN']} DOWN" if counts["DOWN"] else "")
        + " ──"
    )

    # Push results to Supabase
    try:
        supabase = _get_supabase()
    except Exception as exc:
        supabase = None
        print(f"  [warn] Could not initialize Supabase client: {exc}")

    if supabase and all_results:
        rows = [
            {
                "name": r.get("name"),
                "url": r.get("url"),
                "status": r.get("status", "DOWN"),
                "http_status": r.get("http_status"),
                "http_response_ms": r.get("http_response_ms"),
                "widget_detected": r.get("widget_detected"),
                "chat_responded": r.get("chat_responded"),
                "chat_response_ms": r.get("chat_response_ms"),
                "error": r.get("error"),
                "checked_at": timestamp,
            }
            for r in all_results
        ]
        try:
            supabase.table("concierge_checks").insert(rows).execute()
            print(f"  → Pushed {len(rows)} results to Supabase.")
        except Exception as exc:
            print(f"  [warn] Supabase push failed: {exc}")

    if failures:
        summary = ", ".join(failures[:5])
        if len(failures) > 5:
            summary += f" (+{len(failures) - 5} more)"
        _notify("Chat Monitor ⚠️", summary)


def _print_result(result: dict[str, Any]) -> None:
    """Pretty-print a single check result to the terminal."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    name = result["name"]
    url = result["url"]

    http_status = result.get("http_status", "—")
    http_ms = result.get("http_response_ms")
    http_str = f"{http_status} ({http_ms}ms)" if http_ms is not None else str(http_status)

    widget = "OK" if result.get("widget_detected") else "NOT FOUND"
    iframe_note = " (iframe)" if result.get("widget_in_iframe") else ""

    chat_ms = result.get("chat_response_ms")
    chat_text = result.get("chat_response_text") or ""
    if result.get("chat_responded") and chat_ms is not None:
        chat_str = f'OK ({chat_ms / 1000:.1f}s) — "{chat_text[:60]}"'
    else:
        chat_str = "NO RESPONSE"

    status = result.get("status", "UNKNOWN")
    error = result.get("error")

    print(f"\n[{ts}]")
    print(f"{name} — {url}")
    print(f"  HTTP:   {http_str}")
    print(f"  Widget: {widget}{iframe_note}")
    print(f"  Chat:   {chat_str}")
    print(f"  Status: {status}")
    if error:
        print(f"  Error:  {error}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    config = load_and_validate_config(CONFIG_PATH)

    logger = setup_logger(
        log_max_bytes=config["log_max_bytes"],
        log_backup_count=config["log_backup_count"],
    )
    logger.info("Chat monitor started.")

    stop_event = asyncio.Event()

    def _shutdown(sig_name: str) -> None:
        print(f"\n[signal] {sig_name} received — shutting down after current cycle...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig.name: _shutdown(s))

    async def _run_checks_wrapper(cfg: dict[str, Any]) -> None:
        await run_checks(cfg, logger)

    await run_scheduler(
        config=config,
        run_checks=_run_checks_wrapper,
        stop_event=stop_event,
    )

    logger.info("Chat monitor stopped.")


if __name__ == "__main__":
    asyncio.run(main())
