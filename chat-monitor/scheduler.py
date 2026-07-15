"""
scheduler.py — Anchor-based async scheduling loop.

Computes run windows from a wall-clock anchor time so the schedule
stays predictable across process restarts (no drift).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Coroutine


def _next_run_time(
    anchor: str, check_times_per_day: int
) -> datetime:
    """
    Given an anchor like "00:00" and N checks/day, return the next
    datetime (UTC-aware) when a check should fire.

    Example: anchor="00:00", checks=2  → fires at 00:00 and 12:00 UTC.
    """
    now = datetime.now(timezone.utc)
    interval_seconds = 86400 / check_times_per_day

    anchor_h, anchor_m = (int(x) for x in anchor.split(":"))
    today_anchor = now.replace(
        hour=anchor_h, minute=anchor_m, second=0, microsecond=0
    )

    # Generate all fire times for today starting from anchor
    candidates = [
        today_anchor + timedelta(seconds=interval_seconds * i)
        for i in range(check_times_per_day)
    ]
    # Add tomorrow's first window in case we're past today's last
    candidates.append(today_anchor + timedelta(days=1))

    future = [t for t in candidates if t > now]
    return min(future)


async def run_scheduler(
    config: dict[str, Any],
    run_checks: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    stop_event: asyncio.Event,
) -> None:
    """
    Loop forever, sleeping until the next scheduled window, then calling
    run_checks(config). Exits cleanly when stop_event is set.

    Args:
        config:      Full parsed config dict.
        run_checks:  Async callable that performs one full check cycle.
        stop_event:  Set this to trigger a graceful shutdown.
    """
    anchor = config.get("schedule_anchor", "00:00")
    check_times_per_day = config.get("check_times_per_day", 2)

    while not stop_event.is_set():
        next_run = _next_run_time(anchor, check_times_per_day)
        now = datetime.now(timezone.utc)
        sleep_seconds = (next_run - now).total_seconds()

        print(
            f"[scheduler] Next check at {next_run.strftime('%Y-%m-%d %H:%M UTC')} "
            f"(in {sleep_seconds / 3600:.1f}h)"
        )

        # Sleep in short intervals so stop_event is checked frequently
        slept = 0.0
        while slept < sleep_seconds and not stop_event.is_set():
            chunk = min(30.0, sleep_seconds - slept)
            await asyncio.sleep(chunk)
            slept += chunk

        if stop_event.is_set():
            break

        await run_checks(config)
