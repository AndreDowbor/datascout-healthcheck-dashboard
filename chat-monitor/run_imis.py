"""
run_imis.py — Run iMIS member portal checks on demand.

Usage:
    python3 run_imis.py
"""

import asyncio
from main import load_and_validate_config, run_checks
from logger import setup_logger


async def main():
    config = load_and_validate_config("config.json")
    config["urls"] = [e for e in config["urls"] if e.get("type") == "imis_member"]

    if not config["urls"]:
        print("[warn] No imis_member entries found in config.json")
        return

    logger = setup_logger(
        log_max_bytes=config["log_max_bytes"],
        log_backup_count=config["log_backup_count"],
    )
    await run_checks(config, logger)


if __name__ == "__main__":
    asyncio.run(main())
