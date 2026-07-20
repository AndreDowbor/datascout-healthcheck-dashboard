"""
fix_rest_availability.py — enables "Available via the REST API" on a specific
IQA/Trigger across environments where the healthcheck reports it as Broken.

ROOT CAUSE (confirmed 2026-07-20 by comparing demo42 vs atsdemo89 side by side):
Triggers/resubscribe returns "Query: ... not found" (HTTP 400) via /api/IQA
in ~23 environments not because the query is missing, but because its
Security tab checkbox "Available via the REST API" is unchecked there —
everything else (access mode, Staff/SysAdmin permissions) is identical to
the working golden record (demo42). This is a UI-only setting; there is no
REST API to flip it, hence this Playwright tool.

SAFETY:
  - Reads the current checkbox state first. If it's already checked, the
    environment is skipped (logged as "already_ok") — nothing is clicked.
  - After checking the box and clicking Save, the item is re-opened fresh
    and the checkbox state is re-read to confirm the save actually took
    (not just a client-side postback) before marking it "fixed".
  - Only ever touches the exact TARGET_ITEMS below — nothing is derived
    dynamically.

Usage:
    python3 iqa_rest_fix/fix_rest_availability.py
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from common.onepassword_manager import OnePasswordManager

# ── Hardcoded target — do not derive this dynamically ───────────────────────
IQA_FOLDER_PATH = ["_DataScout", "AiParts", "Profile"]
IQA_ITEM_NAME = "Datascout AiParts - Profile Security"

# The 3 envs where the IQA healthcheck reports this item as Broken.
ENV_NAMES = [
    "demo14", "atsdemo90", "demosales44",
]

# Some environments land on the public homepage instead of the staff console
# when navigating to base_url + "/" — go straight to the staff login page instead.
LOGIN_URL_OVERRIDES = {
    "demosales3": "https://demosales3.imiscloud.com/Staff",
}

RISE_LINK_SELECTOR = "a.RiSELink"
IQA_LINK_SELECTOR = "a[href*='/Staff/AsiCommon/Controls/IQA/Default.aspx']"
SECURITY_TAB_SELECTOR = "a.IQASecurityTab"
REST_CHECKBOX_ID = "ctl00_TemplateBody_DesignShell1_ctl00_LimitRestAvailabilityCheckbox"
SAVE_BUTTON_SELECTOR = "a.IQASaveButton, #ctl00_TemplateBody_DesignShell1_ctl00_SaveButton"

SCREENSHOT_DIR = REPO_ROOT / "iqa_rest_fix" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

USERNAME_SELECTOR = "[id$='signInUserName']"
PASSWORD_SELECTOR = "[id$='signInPassword']"
LOGIN_BUTTON_SELECTOR = "[id$='SubmitButton']"
NEW_LOGIN_USERNAME_SELECTOR = "[id$='OpenIdUserName']"
NEW_LOGIN_CONTINUE_SELECTOR = "[id$='OpenIdSubmitButton']"
NEW_LOGIN_PASSWORD_TOGGLE_SELECTOR = "text=Sign in using iMIS password"
NEW_LOGIN_PASSWORD_SELECTOR = "[id$='OpenIdPassword']"
NEW_LOGIN_SIGNIN_SELECTOR = "[id$='ReservedUserSubmitButton']"


def normalize_base_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


async def login(page, base_url: str, username: str, password: str, login_url: str = None):
    url = login_url or f"{normalize_base_url(base_url)}/"
    await page.goto(url, wait_until="load", timeout=60000)

    try:
        await page.click("text=Accept All", timeout=3000)
    except Exception:
        pass

    use_new_login = False
    login_form_visible = False
    try:
        await page.wait_for_selector(USERNAME_SELECTOR, timeout=5000)
        login_form_visible = True
    except Exception:
        try:
            await page.wait_for_selector(NEW_LOGIN_USERNAME_SELECTOR, timeout=3000)
            login_form_visible = True
            use_new_login = True
        except Exception:
            pass

    if not login_form_visible:
        for sel in ["a:has-text('Sign in')", "a:has-text('Sign In')",
                    "a:has-text('Log in')", "a:has-text('Log In')",
                    "a[href*='Login']", "a[href*='login']", "a[href*='SignIn']"]:
            try:
                elem = page.locator(sel).first
                if await elem.is_visible(timeout=2000):
                    await elem.click()
                    login_form_visible = True
                    break
            except Exception:
                continue
        if not login_form_visible:
            raise RuntimeError("Could not find login form or a Sign In link")
        try:
            await page.wait_for_selector(USERNAME_SELECTOR, timeout=8000)
        except Exception:
            await page.wait_for_selector(NEW_LOGIN_USERNAME_SELECTOR, timeout=8000)
            use_new_login = True

    if use_new_login:
        await page.fill(NEW_LOGIN_USERNAME_SELECTOR, username)
        await page.click(NEW_LOGIN_CONTINUE_SELECTOR)
        await page.click(NEW_LOGIN_PASSWORD_TOGGLE_SELECTOR, timeout=8000)
        await page.wait_for_selector(NEW_LOGIN_PASSWORD_SELECTOR, state="visible", timeout=8000)
        await page.fill(NEW_LOGIN_PASSWORD_SELECTOR, password)
        await page.click(NEW_LOGIN_SIGNIN_SELECTOR)
    else:
        await page.fill(USERNAME_SELECTOR, username)
        await page.fill(PASSWORD_SELECTOR, password)
        await page.click(LOGIN_BUTTON_SELECTOR)

    await page.wait_for_selector(USERNAME_SELECTOR, state="detached", timeout=20000)


async def find_frame_with_selector(page, selector: str, timeout: int = 10000):
    elapsed, step = 0, 500
    while elapsed <= timeout:
        for frame in page.frames:
            try:
                if await frame.locator(selector).count() > 0:
                    return frame
            except Exception:
                continue
        await page.wait_for_timeout(step)
        elapsed += step
    return None


async def open_item_and_get_security_frame(page):
    """Navigate RiSE > IQA > folder path > double-click item > Security tab.
    Returns the frame holding the Security panel, or None."""
    await page.locator(RISE_LINK_SELECTOR).first.click()
    await page.locator(IQA_LINK_SELECTOR).first.click()
    await page.wait_for_timeout(1500)

    for name in IQA_FOLDER_PATH:
        node = page.locator(f"span.rtIn.TreeNode:text-is('{name}')").first
        await node.wait_for(state="visible", timeout=10000)
        await node.click()
        await page.wait_for_timeout(1200)

    item = page.locator(f"text={IQA_ITEM_NAME}").first
    await item.wait_for(state="visible", timeout=10000)
    await item.dblclick()
    await page.wait_for_timeout(2000)

    cb_frame = await find_frame_with_selector(page, f"#{REST_CHECKBOX_ID}", timeout=5000)
    if cb_frame is not None:
        return cb_frame

    sec_frame = await find_frame_with_selector(page, SECURITY_TAB_SELECTOR, timeout=10000)
    if sec_frame is None:
        return None
    await sec_frame.locator(SECURITY_TAB_SELECTOR).first.click(timeout=8000)
    await page.wait_for_timeout(1500)
    return await find_frame_with_selector(page, f"#{REST_CHECKBOX_ID}", timeout=8000)


async def process_env(playwright, env_name: str, creds: dict) -> str:
    """Returns: 'fixed' | 'already_ok' | 'error' | 'verify_failed'"""
    print(f"\n── {env_name} ──")
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()

    try:
        await login(page, creds["base_url"], creds["username"], creds["password"],
                    login_url=LOGIN_URL_OVERRIDES.get(env_name))

        frame = await open_item_and_get_security_frame(page)
        if frame is None:
            print("    Could not reach the Security panel / checkbox.")
            await page.screenshot(path=str(SCREENSHOT_DIR / f"fail_{env_name}_no_checkbox.png"), full_page=True)
            await browser.close()
            return "error"

        checked = await frame.evaluate(f"document.getElementById('{REST_CHECKBOX_ID}').checked")
        print(f"    Current state — Available via the REST API: {checked}")

        if checked:
            print("    Already enabled — nothing to do.")
            await browser.close()
            return "already_ok"

        await frame.locator(f"#{REST_CHECKBOX_ID}").click(timeout=8000)
        await page.wait_for_timeout(1000)

        save_btn = frame.locator(SAVE_BUTTON_SELECTOR).first
        if await save_btn.count() == 0:
            save_btn = frame.get_by_text("Save", exact=True).first
        await save_btn.click(timeout=8000)
        await page.wait_for_timeout(2500)
        print("    Checked the box and clicked Save.")
        await page.screenshot(path=str(SCREENSHOT_DIR / f"after_save_{env_name}.png"), full_page=True)

        # Re-open fresh and re-read the checkbox to confirm the save persisted.
        try:
            await page.locator("text=Close").first.click(timeout=5000)
            await page.wait_for_timeout(1000)
        except Exception:
            pass

        frame2 = await open_item_and_get_security_frame(page)
        if frame2 is None:
            print("    Could not re-verify — Security panel not found on reopen.")
            await browser.close()
            return "verify_failed"
        checked_after = await frame2.evaluate(f"document.getElementById('{REST_CHECKBOX_ID}').checked")
        print(f"    Re-verified state after reopen: {checked_after}")
        await browser.close()
        return "fixed" if checked_after else "verify_failed"

    except Exception as e:
        print(f"  ❌ Failed to process {env_name}: {e}")
        try:
            await page.screenshot(path=str(SCREENSHOT_DIR / f"fail_{env_name}.png"), full_page=True)
        except Exception:
            pass
        await browser.close()
        return "error"


async def main():
    op = OnePasswordManager()
    print("Fetching credentials from 1Password...")
    environment_credentials = {}
    for env_name in ENV_NAMES:
        try:
            secrets = await op.get_flattened_client_item(env_name)
            base_url = secrets.get("imis_base_url")
            username = secrets.get("imis_user") or secrets.get("username") or secrets.get("user")
            password = secrets.get("imis_password") or secrets.get("password")
            if not all([base_url, username, password]):
                print(f"  SKIP  {env_name}: missing field(s).")
                continue
            environment_credentials[env_name] = {"base_url": base_url, "username": username, "password": password}
        except Exception as e:
            print(f"  FAIL  {env_name}: {e}")

    print(f"Loaded {len(environment_credentials)}/{len(ENV_NAMES)} environments.")
    print(f"Target: {'/'.join(IQA_FOLDER_PATH)}/{IQA_ITEM_NAME} — enable 'Available via the REST API'\n")

    results = {}
    async with async_playwright() as p:
        for env_name, creds in environment_credentials.items():
            results[env_name] = await process_env(p, env_name, creds)

    print("\n\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for env_name, status in results.items():
        print(f"  {status:14s} {env_name}")


if __name__ == "__main__":
    asyncio.run(main())
