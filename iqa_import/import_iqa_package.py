"""
import_iqa_package.py — Playwright tool to import an IQA package into an
iMIS environment via RiSE > Intelligent Query Architect > Import.

See iqa_import/README.md for the full click path, known selectors, and how
to point this at a different environment/package for future corrections.

Usage:
    Edit ENV_NAME, IQA_FOLDER_NAME and PACKAGE_PATH below, then:
    python3 iqa_import/import_iqa_package.py

Runs with a HEADED browser so you can watch it live. Pauses at the end
(Playwright Inspector) so you can review the Messages box / screenshots
before closing.
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

# ── Edit these for each run ─────────────────────────────────────────────────
ENV_NAME = "demo86"
IQA_FOLDER_NAME = "_DataScout"
PACKAGE_PATH = Path("/Users/andrewdowbor/Downloads/Segments (2).xml")
# ─────────────────────────────────────────────────────────────────────────────

RISE_LINK_SELECTOR = "a.RiSELink"
IQA_LINK_SELECTOR = "a[href*='/Staff/AsiCommon/Controls/IQA/Default.aspx']"
FOLDER_NODE_SELECTOR = f"span.rtIn.TreeNode:text-is('{IQA_FOLDER_NAME}')"
IMPORT_MENU_SELECTOR = "span.rmText:text-is('Import')"
FILE_INPUT_SELECTOR = "#ctl00_TemplateBody_FileUploadfile0"
UPLOAD_BUTTON_SELECTOR = "#ctl00_TemplateBody_UploadButton"
IMPORT_BUTTON_SELECTOR = "#ctl00_TemplateBody_ImportButton"

SCREENSHOT_DIR = REPO_ROOT / "iqa_import" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

USERNAME_SELECTOR = "[id$='signInUserName']"
PASSWORD_SELECTOR = "[id$='signInPassword']"
LOGIN_BUTTON_SELECTOR = "[id$='SubmitButton']"

# Newer iMIS "email first" sign-in widget.
NEW_LOGIN_USERNAME_SELECTOR = "[id$='OpenIdUserName']"
NEW_LOGIN_CONTINUE_SELECTOR = "[id$='OpenIdSubmitButton']"
NEW_LOGIN_PASSWORD_TOGGLE_SELECTOR = "text=Sign in using iMIS password"
NEW_LOGIN_PASSWORD_SELECTOR = "[id$='OpenIdPassword']"
NEW_LOGIN_SIGNIN_SELECTOR = "[id$='ReservedUserSubmitButton']"


def normalize_base_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


async def login(page, base_url: str, username: str, password: str):
    login_url = f"{normalize_base_url(base_url)}/"
    print(f"Navigating to {login_url}")
    await page.goto(login_url, wait_until="load", timeout=60000)

    use_new_login = False
    try:
        await page.wait_for_selector(USERNAME_SELECTOR, timeout=5000)
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
    print("Logged in.")


async def click_step(page, selector: str, label: str, timeout: int = 20000):
    print(f"Clicking: {label} ({selector})")
    try:
        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=timeout)
        await locator.click()
    except Exception:
        debug_path = SCREENSHOT_DIR / f"fail_{label.replace(' ', '_').lower()}.png"
        await page.screenshot(path=str(debug_path), full_page=True)
        print(f"Failed at step '{label}'. Debug screenshot: {debug_path}")
        print(f"Current URL: {page.url}")
        raise


async def find_frame_with_selector(page, selector: str, timeout: int = 15000):
    """Search every frame on the page for `selector`, polling until found or timeout."""
    elapsed = 0
    step = 500
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


async def main():
    op = OnePasswordManager()
    print(f"Fetching credentials for {ENV_NAME} from 1Password...")
    creds = await op.get_flattened_client_item(ENV_NAME)

    username = creds.get("imis_user") or creds.get("username") or creds.get("user")
    password = creds.get("imis_password") or creds.get("password")
    base_url = creds.get("imis_base_url") or creds.get("base_url") or creds.get("imis_url")

    missing = [k for k, v in {"username": username, "password": password, "base_url": base_url}.items() if not v]
    if missing:
        raise ValueError(f"Missing 1Password field(s) for {ENV_NAME}: {missing}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await login(page, base_url, username, password)
        print("\nLogged into", ENV_NAME, "—", page.url)

        try:
            await page.click("text=Accept All", timeout=3000)
            print("Dismissed cookie banner.")
        except Exception:
            pass

        await click_step(page, RISE_LINK_SELECTOR, "RiSE menu")
        await click_step(page, IQA_LINK_SELECTOR, "Intelligent Query Architect")
        await click_step(page, FOLDER_NODE_SELECTOR, f"{IQA_FOLDER_NAME} folder node")
        await click_step(page, IMPORT_MENU_SELECTOR, "Import menu item")

        screenshot_path = SCREENSHOT_DIR / "import_dialog.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"\nReached the Import dialog. Screenshot: {screenshot_path}")

        print(f"Looking for the file input across all frames: {FILE_INPUT_SELECTOR}")
        print("Frames on page:", [f.url for f in page.frames])
        file_frame = await find_frame_with_selector(page, FILE_INPUT_SELECTOR)
        if file_frame is None:
            print("File input never appeared in any frame. Pausing for manual inspection.")
            await page.pause()
            await browser.close()
            return

        print(f"Found file input in frame: {file_frame.url}")
        await file_frame.locator(FILE_INPUT_SELECTOR).set_input_files(str(PACKAGE_PATH))

        before_upload_path = SCREENSHOT_DIR / "before_upload_click.png"
        await page.screenshot(path=str(before_upload_path), full_page=True)
        print(f"File selected. Screenshot: {before_upload_path}")

        await file_frame.locator(UPLOAD_BUTTON_SELECTOR).click()
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass

        after_upload_path = SCREENSHOT_DIR / "after_upload_click.png"
        await page.screenshot(path=str(after_upload_path), full_page=True)
        print(f"\nClicked Upload. Screenshot: {after_upload_path}")

        print("Clicking final Import button — this performs the real write.")
        await file_frame.locator(IMPORT_BUTTON_SELECTOR).click()

        print("Waiting for the import to finish (up to ~120s) — capturing progress every 5s...")
        last_text = None
        for i in range(24):
            await page.wait_for_timeout(5000)
            elapsed = (i + 1) * 5

            progress_path = SCREENSHOT_DIR / f"progress_{elapsed:03d}s.png"
            await page.screenshot(path=str(progress_path), full_page=True)

            try:
                text = await file_frame.locator("textarea").first.input_value()
            except Exception:
                text = None

            if text and text != last_text:
                print(f"  [{elapsed}s] Messages box changed:\n{text}\n")
                last_text = text
            else:
                print(f"  ...still waiting ({elapsed}s elapsed)")

        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        after_import_path = SCREENSHOT_DIR / "after_import_click.png"
        await page.screenshot(path=str(after_import_path), full_page=True)
        print(f"\nImport postback should be done. Screenshot: {after_import_path}")
        if last_text:
            print(f"Final captured Messages text:\n{last_text}")
        else:
            print("Never captured non-empty Messages text — check the progress_*.png screenshots.")
        await page.pause()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
