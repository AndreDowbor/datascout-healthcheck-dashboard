"""
monitor.py — HTTP check, widget detection, and conversational test.

Each public function is a pure async operation that returns a result dict.
No side effects beyond returning data — logging is handled by the caller.
"""

import asyncio
import random
import time
from typing import Any

import httpx
from playwright.async_api import (
    Browser,
    BrowserContext,
    Frame,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

# Selectors used to find a chat input in a frame.
INPUT_SELECTORS = [
    'input[type="text"]',
    "input:not([type])",
    "textarea",
]

# Fallback selectors for detecting new response messages.
RESPONSE_FALLBACK_SELECTORS = [
    ".prose",          # Tailwind prose — used by this app's bot messages
    '[role="log"] *',
    ".message",
    ".chat-message",
    ".msg",
    "li",
]


# ---------------------------------------------------------------------------
# HTTP Check
# ---------------------------------------------------------------------------


async def http_check(url: str, timeout: float = 10.0) -> dict[str, Any]:
    """
    Perform an async HTTP GET and return status/timing.

    Returns:
        {
            "http_status": int | None,
            "http_response_ms": int | None,
            "http_ok": bool,
            "error": str | None,
        }
    """
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=timeout)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        ok = response.status_code == 200
        return {
            "http_status": response.status_code,
            "http_response_ms": elapsed_ms,
            "http_ok": ok,
            "error": None if ok else f"HTTP {response.status_code}",
        }
    except httpx.TimeoutException:
        return {
            "http_status": None,
            "http_response_ms": None,
            "http_ok": False,
            "error": "HTTP timeout",
        }
    except httpx.ConnectError as exc:
        return {
            "http_status": None,
            "http_response_ms": None,
            "http_ok": False,
            "error": f"Connection error: {exc}",
        }
    except httpx.HTTPError as exc:
        return {
            "http_status": None,
            "http_response_ms": None,
            "http_ok": False,
            "error": f"HTTP error: {exc}",
        }


# ---------------------------------------------------------------------------
# Widget Detection
# ---------------------------------------------------------------------------


async def _find_input_in_frame(frame: Frame, timeout_ms: int) -> str | None:
    """
    Try each INPUT_SELECTORS in the given frame.
    Returns the matching selector string or None.
    """
    for selector in INPUT_SELECTORS:
        try:
            await frame.wait_for_selector(selector, timeout=timeout_ms)
            return selector
        except PlaywrightTimeoutError:
            continue
    return None


async def detect_widget(
    page: Page, widget_timeout: float = 30.0
) -> dict[str, Any]:
    """
    Scan main frame then all child iframes for a chat input.

    Returns:
        {
            "widget_detected": bool,
            "widget_in_iframe": bool,
            "matched_selector": str | None,
            "active_frame": Frame | None,   # the frame that contains the input
            "error": str | None,
        }
    """
    timeout_ms = int(widget_timeout * 1000)

    # 1. Try main frame first
    selector = await _find_input_in_frame(page.main_frame, timeout_ms=2000)
    if selector:
        return {
            "widget_detected": True,
            "widget_in_iframe": False,
            "matched_selector": selector,
            "active_frame": page.main_frame,
            "error": None,
        }

    # 2. Scan child frames
    deadline = time.monotonic() + widget_timeout
    while time.monotonic() < deadline:
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            remaining_ms = max(int((deadline - time.monotonic()) * 1000), 500)
            selector = await _find_input_in_frame(frame, timeout_ms=remaining_ms)
            if selector:
                return {
                    "widget_detected": True,
                    "widget_in_iframe": True,
                    "matched_selector": selector,
                    "active_frame": frame,
                    "error": None,
                }
        await asyncio.sleep(0.5)

    return {
        "widget_detected": False,
        "widget_in_iframe": False,
        "matched_selector": None,
        "active_frame": None,
        "error": "Widget not found within timeout",
    }


# ---------------------------------------------------------------------------
# Conversational Test
# ---------------------------------------------------------------------------


async def _count_messages(
    frame: Frame, container_selector: str | None
) -> int:
    """Count message elements in the active frame before/after sending."""
    if container_selector:
        try:
            container = frame.locator(container_selector)
            count = await container.locator("> *").count()
            if count > 0:
                return count
        except Exception:
            pass

    # Fallback: try generic message selectors
    for sel in RESPONSE_FALLBACK_SELECTORS:
        try:
            count = await frame.locator(sel).count()
            if count > 0:
                return count
        except Exception:
            continue
    return 0


async def _get_newest_message_text(
    frame: Frame, container_selector: str | None
) -> str:
    """Return the text content of the last message element."""
    if container_selector:
        try:
            children = frame.locator(container_selector).locator("> *")
            count = await children.count()
            if count > 0:
                text = (await children.nth(count - 1).inner_text()).strip()
                if text:
                    return text
        except Exception:
            pass

    for sel in RESPONSE_FALLBACK_SELECTORS:
        try:
            elements = frame.locator(sel)
            count = await elements.count()
            if count > 0:
                text = (await elements.nth(count - 1).inner_text()).strip()
                if text:
                    return text
        except Exception:
            continue
    return ""


async def conversational_test(
    frame: Frame,
    matched_selector: str,
    test_message: str,
    response_container_selector: str | None,
    chat_timeout: float = 60.0,
) -> dict[str, Any]:
    """
    Type the test message and wait for a new response to appear.

    Returns:
        {
            "chat_responded": bool,
            "chat_response_ms": int | None,
            "chat_response_text": str | None,
            "error": str | None,
        }
    """
    try:
        input_el = frame.locator(matched_selector).first

        # Wait for the initial bot greeting to appear before snapshotting,
        # so we don't mistake the greeting for a response to our message.
        greeting_deadline = time.monotonic() + 10.0
        while time.monotonic() < greeting_deadline:
            if await _count_messages(frame, response_container_selector) > 0:
                break
            await asyncio.sleep(0.5)

        # Snapshot message count before sending
        before_count = await _count_messages(frame, response_container_selector)

        # Click input and type with human-like delay
        await input_el.click()
        for char in test_message:
            await input_el.type(char, delay=random.randint(40, 120))

        await input_el.press("Enter")
        send_time = time.monotonic()

        # Poll for a new message
        deadline = send_time + chat_timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            after_count = await _count_messages(frame, response_container_selector)
            if after_count > before_count:
                text = await _get_newest_message_text(
                    frame, response_container_selector
                )
                if text:
                    elapsed_ms = int((time.monotonic() - send_time) * 1000)
                    return {
                        "chat_responded": True,
                        "chat_response_ms": elapsed_ms,
                        "chat_response_text": text,
                        "error": None,
                    }

        return {
            "chat_responded": False,
            "chat_response_ms": None,
            "chat_response_text": None,
            "error": "No response within chat timeout",
        }

    except PlaywrightTimeoutError as exc:
        return {
            "chat_responded": False,
            "chat_response_ms": None,
            "chat_response_text": None,
            "error": f"Playwright timeout: {exc}",
        }
    except Exception as exc:
        return {
            "chat_responded": False,
            "chat_response_ms": None,
            "chat_response_text": None,
            "error": f"Unexpected error: {exc}",
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _classify_status(
    http_ok: bool, widget_detected: bool, chat_responded: bool
) -> str:
    if not http_ok:
        return "DOWN"
    if not widget_detected:
        return "DEGRADED (no-widget)"
    if not chat_responded:
        return "DEGRADED (no-response)"
    return "UP"


async def check_url(
    entry: dict[str, Any],
    global_config: dict[str, Any],
    browser: Browser,
) -> dict[str, Any]:
    """
    Run the full check pipeline for a single URL entry.

    Args:
        entry:         One item from config["urls"]
        global_config: Full parsed config dict
        browser:       Shared Playwright Browser instance

    Returns a structured result dict ready for logging.
    """
    name = entry["name"]
    url = entry["url"]
    http_timeout = entry.get("http_timeout", 10)
    widget_timeout = entry.get("widget_timeout", 30)
    chat_timeout = entry.get("chat_timeout", 60)
    response_selector = entry.get("response_container_selector")
    test_message = global_config["test_message"]
    headless = global_config.get("playwright_headless", True)

    result: dict[str, Any] = {
        "name": name,
        "url": url,
        "http_status": None,
        "http_response_ms": None,
        "widget_detected": False,
        "widget_in_iframe": False,
        "chat_responded": False,
        "chat_response_ms": None,
        "chat_response_text": None,
        "status": "DOWN",
        "error": None,
    }

    # --- HTTP check ---
    http_result = await http_check(url, timeout=http_timeout)
    result.update(
        {
            "http_status": http_result["http_status"],
            "http_response_ms": http_result["http_response_ms"],
        }
    )
    if not http_result["http_ok"]:
        result["status"] = "DOWN"
        result["error"] = http_result["error"]
        return result

    # --- Browser checks ---
    context: BrowserContext | None = None
    try:
        context = await browser.new_context()
        page: Page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=widget_timeout * 1000)
        except PlaywrightTimeoutError:
            result["status"] = "DEGRADED (no-widget)"
            result["error"] = "Page load timeout"
            return result

        # Widget detection
        widget_result = await detect_widget(page, widget_timeout=widget_timeout)
        result["widget_detected"] = widget_result["widget_detected"]
        result["widget_in_iframe"] = widget_result["widget_in_iframe"]

        if not widget_result["widget_detected"]:
            result["status"] = "DEGRADED (no-widget)"
            result["error"] = widget_result["error"]
            return result

        # Conversational test
        chat_result = await conversational_test(
            frame=widget_result["active_frame"],
            matched_selector=widget_result["matched_selector"],
            test_message=test_message,
            response_container_selector=response_selector,
            chat_timeout=chat_timeout,
        )
        result["chat_responded"] = chat_result["chat_responded"]
        result["chat_response_ms"] = chat_result["chat_response_ms"]
        result["chat_response_text"] = chat_result["chat_response_text"]
        if chat_result["error"]:
            result["error"] = chat_result["error"]

    except Exception as exc:
        result["error"] = f"Browser error: {exc}"
    finally:
        if context:
            await context.close()

    result["status"] = _classify_status(
        http_ok=True,
        widget_detected=result["widget_detected"],
        chat_responded=result["chat_responded"],
    )
    return result
