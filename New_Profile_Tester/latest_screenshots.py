"""
latest_screenshots.py — Resolve the most recent screenshot per environment,
so a reviewer (human or Claude) can look at exactly one image per env from
the latest test run instead of hunting through timestamped filenames.

Screenshot filenames look like:
    <env>_profile_panel_<YYYY-MM-DD>_<HH-MM-SS>.png
    <env>_datascout_debug_<YYYY-MM-DD>_<HH-MM-SS>.png
    <env>_login_debug_<YYYY-MM-DD>_<HH-MM-SS>.png
    <env>_crossdomain_debug_<YYYY-MM-DD>_<HH-MM-SS>.png

For a given date folder, this picks the single newest file per env
regardless of kind — a debug screenshot is kept if it's an env's only (or
latest) shot, since that's the actual record of what happened to it in that
run.

Usage:
    python3 latest_screenshots.py                  # today's date folder
    python3 latest_screenshots.py 2026-07-30        # a specific date folder
"""

import re
import sys
from datetime import datetime
from pathlib import Path

SCREENSHOT_ROOT = Path(__file__).parent / "screenshots"

NAME_RE = re.compile(
    r"^(?P<env>.+?)_(?:profile_panel|datascout_debug|login_debug|crossdomain_debug)"
    r"_(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2})\.png$"
)


def latest_per_env(date: str | None = None) -> dict[str, Path]:
    """
    Return {env_name: path} for the newest screenshot of each env in the
    given date folder (defaults to today; falls back to the most recent
    date folder that exists if today's has nothing yet).
    """
    target = date or datetime.now().strftime("%Y-%m-%d")
    folder = SCREENSHOT_ROOT / target

    if not folder.is_dir():
        dated_folders = sorted(
            (p for p in SCREENSHOT_ROOT.iterdir() if p.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", p.name)),
            reverse=True,
        )
        if not dated_folders:
            return {}
        folder = dated_folders[0]

    latest: dict[str, tuple[str, Path]] = {}
    for path in folder.glob("*.png"):
        m = NAME_RE.match(path.name)
        if not m:
            continue
        env = m.group("env").lower()
        stamp = f"{m.group('date')}_{m.group('time')}"
        if env not in latest or stamp > latest[env][0]:
            latest[env] = (stamp, path)

    return {env: path for env, (_, path) in sorted(latest.items())}


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    results = latest_per_env(date_arg)
    if not results:
        print("No screenshots found.")
        sys.exit(1)
    for env, path in results.items():
        print(f"{env:15s} {path}")
    print(f"\n{len(results)} environments.")
