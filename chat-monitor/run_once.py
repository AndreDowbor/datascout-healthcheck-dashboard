"""
run_once.py — Run a single Concierge chat check cycle across all URLs
(web + imis_member), bypassing the scheduler loop in main.py.

For running via cron/launchd twice a day instead of keeping main.py's
built-in scheduler loop alive as a long-running process.

Usage:
    python3 run_once.py
"""

import asyncio
from main import load_and_validate_config, run_checks, CONFIG_PATH
from logger import setup_logger


async def go():
    config = load_and_validate_config(CONFIG_PATH)
    logger = setup_logger(
        log_max_bytes=config["log_max_bytes"],
        log_backup_count=config["log_backup_count"],
    )
    await run_checks(config, logger)


if __name__ == "__main__":
    asyncio.run(go())
