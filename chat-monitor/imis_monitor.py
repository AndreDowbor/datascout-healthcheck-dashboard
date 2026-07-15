"""
imis_monitor.py — Chat widget check via iMIS member portal login.

Extends the direct URL check with a login step using 1Password credentials.
Credentials are fetched from 1Password using the env name as the item key.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from monitor import _classify_status, conversational_test, http_check, INPUT_SELECTORS

# Make OnePasswordManager importable from New_Profile_Tester/
sys.path.insert(0, str(Path(__file__).parent / "New_Profile_Tester"))
from onepassword_manager import OnePasswordManager  # type: ignore  # noqa: E402

USERNAME_SELECTOR = "[id$='signInUserName']"
PASSWORD_SELECTOR = "[id$='signInPassword']"
LOGIN_BUTTON_SELECTOR = "[id$='SubmitButton']"
CHAT_BUBBLE_SELECTOR = "#chatbotBubble"


async def _wait_for_sso_ready(page: Page, timeout: float = 30.0) -> None:
    """
    Wait for the hidden ssoSetupFrame to finish loading.
    The chatbot JS sets ssoReady=true only after the SSO frame navigates to
    the gateway callback. We detect this by polling page frames.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for frame in page.frames:
            if "gateway" in frame.url and "sso" in frame.url:
                return
        await asyncio.sleep(0.5)


async def _detect_chat_widget_in_iframe(page: Page, widget_timeout: float = 30.0) -> dict[str, Any]:
    """
    Wait for the chatbotIframe to load the engage URL, then find the chat input.
    Skips the main frame and the SSO setup frame to avoid false positives.
    """
    deadline = time.monotonic() + widget_timeout
    while time.monotonic() < deadline:
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            if "gateway" in frame.url:  # SSO frame, not the chat UI
                continue
            if "engage" not in frame.url:
                continue
            remaining_ms = max(int((deadline - time.monotonic()) * 1000), 500)
            for selector in INPUT_SELECTORS:
                try:
                    await frame.wait_for_selector(selector, timeout=remaining_ms)
                    return {
                        "widget_detected": True,
                        "widget_in_iframe": True,
                        "matched_selector": selector,
                        "active_frame": frame,
                        "error": None,
                    }
                except PlaywrightTimeoutError:
                    continue
        await asyncio.sleep(0.5)

    return {
        "widget_detected": False,
        "widget_in_iframe": False,
        "matched_selector": None,
        "active_frame": None,
        "error": "Chat widget not found in iframes within timeout",
    }


async def _login_to_imis(
    page: Page, base_url: str, username: str, password: str, label: str = ""
) -> None:
    """Navigate to iMIS base URL and authenticate."""
    login_url = base_url.rstrip("/") + "/"
    await page.goto(login_url, wait_until="load", timeout=60_000)

    # Check if login form is immediately present, else click Sign In link
    login_form_visible = False
    try:
        await page.wait_for_selector(USERNAME_SELECTOR, timeout=5000)
        login_form_visible = True
    except Exception:
        for sel in [
            "a:has-text('Sign in')",
            "a:has-text('Sign In')",
            "a:has-text('Log in')",
            "a:has-text('Log In')",
            "a[href*='Login']",
            "a[href*='login']",
            "a[href*='SignIn']",
        ]:
            try:
                elem = page.locator(sel).first
                if await elem.is_visible(timeout=2000):
                    await elem.click()
                    login_form_visible = True
                    break
            except Exception:
                continue

    if not login_form_visible:
        raise RuntimeError(f"Could not reach login form for {label or base_url}")

    await page.wait_for_selector(USERNAME_SELECTOR, timeout=20_000)
    await page.fill(USERNAME_SELECTOR, username)
    await page.fill(PASSWORD_SELECTOR, password)
    await page.click(LOGIN_BUTTON_SELECTOR)

    # Wait until login form disappears (redirect signals success)
    try:
        await page.wait_for_selector(USERNAME_SELECTOR, state="detached", timeout=20_000)
    except Exception:
        await page.wait_for_selector("body", timeout=20_000)


async def check_url_imis_login(
    entry: dict[str, Any],
    global_config: dict[str, Any],
    browser: Browser,
    op_manager: OnePasswordManager,
) -> dict[str, Any]:
    """
    Full check pipeline for an iMIS member portal entry.

    Logs in using 1Password credentials, navigates to the member portal URL,
    then runs the standard widget detection and conversational test.

    Config entry fields:
        name                        — display name and default 1Password key
        url                         — member portal page URL (e.g. https://demo83.imiscloud.com/web/)
        imis_key                    — (optional) 1Password item title; defaults to name
        response_container_selector — (optional) CSS selector for response container
        http_timeout                — seconds for HTTP GET check (default 10)
        widget_timeout              — seconds to find chat widget (default 30)
        chat_timeout                — seconds to wait for bot response (default 60)
    """
    name = entry["name"]
    url = entry["url"]
    imis_key = entry.get("imis_key", name)
    http_timeout = entry.get("http_timeout", 10)
    widget_timeout = entry.get("widget_timeout", 30)
    chat_timeout = entry.get("chat_timeout", 60)
    response_selector = entry.get("response_container_selector")
    test_message = global_config["test_message"]

    result: dict[str, Any] = {
        "name": name,
        "url": url,
        "type": "imis_member",
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
    result["http_status"] = http_result["http_status"]
    result["http_response_ms"] = http_result["http_response_ms"]
    if not http_result["http_ok"]:
        result["error"] = http_result["error"]
        return result

    # --- Fetch credentials from 1Password ---
    try:
        creds = await op_manager.get_flattened_client_item(imis_key)
    except Exception as exc:
        result["error"] = f"1Password error: {exc}"
        return result

    username = creds.get("imis_user") or creds.get("username") or creds.get("user")
    password = creds.get("imis_password") or creds.get("password")
    base_url = creds.get("imis_base_url") or creds.get("base_url") or creds.get("imis_url")

    if not all([username, password, base_url]):
        missing = [k for k, v in {"username": username, "password": password, "base_url": base_url}.items() if not v]
        result["error"] = f"Missing credentials in 1Password for '{imis_key}': {missing}"
        return result

    # --- Browser: login then widget check ---
    context: BrowserContext | None = None
    try:
        context = await browser.new_context()
        page: Page = await context.new_page()

        try:
            await _login_to_imis(page, base_url, username, password, label=name)
        except Exception as exc:
            result["error"] = f"Login failed: {exc}"
            return result

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=int(widget_timeout * 1000))
        except PlaywrightTimeoutError:
            result["status"] = "DEGRADED (no-widget)"
            result["error"] = "Page load timeout after login"
            return result

        # Wait for the hidden SSO setup frame to finish loading (sets ssoReady = true)
        # The SSO frame navigates to the gateway callback before the bubble can open the chat.
        try:
            await page.wait_for_selector(CHAT_BUBBLE_SELECTOR, timeout=int(widget_timeout * 1000))
            await _wait_for_sso_ready(page, timeout=widget_timeout)
        except PlaywrightTimeoutError:
            result["status"] = "DEGRADED (no-widget)"
            result["error"] = "Chat bubble (#chatbotBubble) not found"
            return result

        # Click bubble — now ssoReady is true so the chatbotIframe src will be set
        await page.click(CHAT_BUBBLE_SELECTOR)

        widget_result = await _detect_chat_widget_in_iframe(page, widget_timeout=widget_timeout)
        result["widget_detected"] = widget_result["widget_detected"]
        result["widget_in_iframe"] = widget_result["widget_in_iframe"]

        if not widget_result["widget_detected"]:
            result["status"] = "DEGRADED (no-widget)"
            result["error"] = widget_result["error"]
            return result

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
