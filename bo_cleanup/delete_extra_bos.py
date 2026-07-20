"""
delete_extra_bos.py — stages deletion (Organize > Delete) of the known
legacy Business Objects across environments, via the RiSE Business Object
Designer UI (there's no REST API for this).

demo42 is the golden environment. These 3 BOs exist in nearly every other
environment but not in demo42, so they're being removed everywhere else to
match golden. See bo_cleanup/README.md for the full context and click path.

SAFETY — read before running:
  - TARGET_BOS is a hardcoded allowlist. Nothing outside these exact names
    is ever touched. Datascout_Tags is deliberately NOT included — it's a
    panel, not a regular root business object, and the Business Object
    Designer's Organize menu doesn't offer Delete for it at all. It needs a
    separate cleanup path (likely the Panel/Page Designer) — out of scope
    for this script.
  - Before confirming a delete, the script checks that the browser's native
    confirm() dialog message actually contains the target BO's name. If it
    doesn't match, the dialog is dismissed (Cancel) and that BO is skipped
    instead of proceeding blind.
  - This only STAGES the deletion (Organize > Delete > OK). It moves the BO
    to the Recycle Bin and marks it "Working" (draft) — Publish is NEVER
    clicked by this script. The live system is unaffected until someone
    explicitly publishes each root business object.
  - If a target BO isn't found in an environment (already deleted, or never
    existed there), it's skipped and logged — not an error.

Usage:
    python3 bo_cleanup/delete_extra_bos.py
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

# ── Hardcoded allowlist — do not derive this dynamically ────────────────────
TARGET_BOS = [
    "Datascout_Tag_Changes",
    "Datascout_Tag_Refresh_Date_Fields",
]

# demo42 is golden and excluded — it doesn't have these BOs.
# Remaining pending envs (see progress tracker spreadsheet for full status):
# - demo83, demosales50: not yet attempted (excluded from the last run on request).
# - demosales3: sidebar layout differs — RiSE collapsed behind an expanded
#   Registration section, BOA link resolves but stays hidden. Needs bespoke
#   handling (collapse Registration first) or manual cleanup.
# - bsidemo27, isgdemo14, isgdemo106: login succeeds but lands back on the
#   public front-end site with just a staff toolbar, not the internal RiSE
#   console — needs an extra navigation step this script doesn't have yet.
ENV_NAMES = [
    "demo83", "demosales50", "demosales3", "bsidemo27", "isgdemo14", "isgdemo106",
]

RISE_LINK_SELECTOR = "a.RiSELink"
BOA_LINK_SELECTOR = "a[href*='/Staff/AsiCommon/Controls/BOA/Default.aspx']"
QUICK_FIND_SELECTOR = "#ctl01_TemplateBody_ObjectBrowser1_ObjectQuickFindTextBox"
ORGANIZE_MENU_SELECTOR = "span.rmText.rmExpandDown:text-is('Organize')"
DELETE_MENU_SELECTOR = "span.rmText:text-is('Delete')"
CLOSE_BUTTON_SELECTOR = "#ctl00_CancelButton"

SCREENSHOT_DIR = REPO_ROOT / "bo_cleanup" / "screenshots"
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


async def login(page, base_url: str, username: str, password: str):
    login_url = f"{normalize_base_url(base_url)}/"
    await page.goto(login_url, wait_until="load", timeout=60000)

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
        # Some environments land on the public marketing homepage instead of
        # the login form — click through a "Sign in" link first (same pattern
        # as New_Profile_Tester/imis_env_tester_with_1password.py).
        sign_in_selectors = [
            "a:has-text('Sign in')",
            "a:has-text('Sign In')",
            "a:has-text('Log in')",
            "a:has-text('Log In')",
            "a[href*='Login']",
            "a[href*='login']",
            "a[href*='SignIn']",
        ]
        for sel in sign_in_selectors:
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


def make_dialog_handler(state: dict):
    async def handler(dialog):
        state["message"] = dialog.message
        if state["expected_name"] and state["expected_name"] in dialog.message:
            state["accepted"] = True
            await dialog.accept()
        else:
            state["accepted"] = False
            await dialog.dismiss()
    return handler


async def delete_bo_in_env(page, env_name: str, bo_name: str, dialog_state: dict) -> str:
    """Returns: 'deleted' | 'not_found' | 'mismatch' | 'error'"""
    dialog_state["expected_name"] = bo_name
    dialog_state["message"] = None
    dialog_state["accepted"] = None

    bo_item_selector = f"span.ObjectBrowserContentListName:has-text('{bo_name}')"

    try:
        quick_find = page.locator(QUICK_FIND_SELECTOR).first
        await quick_find.click()
        await quick_find.fill("")
        await quick_find.press_sequentially(bo_name, delay=20)
        await page.wait_for_timeout(800)  # let the client-side filter settle

        bo_locator = page.locator(bo_item_selector).first
        try:
            await bo_locator.wait_for(state="visible", timeout=8000)
        except Exception:
            print(f"    {bo_name}: not found in {env_name} — skipping.")
            return "not_found"

        await bo_locator.click()
        await page.wait_for_timeout(400)  # let selection register before opening the menu

        delete_item = page.locator(DELETE_MENU_SELECTOR).first
        for attempt in range(3):
            await page.locator(ORGANIZE_MENU_SELECTOR).first.click()
            try:
                await delete_item.wait_for(state="visible", timeout=3000)
                break
            except Exception:
                if attempt == 2:
                    raise
                await page.wait_for_timeout(300)
        await delete_item.click()

        await page.wait_for_timeout(2000)  # let the confirm() dialog fire/resolve

        if dialog_state["message"] is None:
            print(f"    {bo_name}: no confirm dialog appeared — treating as error.")
            return "error"
        if not dialog_state["accepted"]:
            print(f"    {bo_name}: dialog message didn't mention the BO name — ABORTED for safety.")
            print(f"      Dialog said: {dialog_state['message']}")
            return "mismatch"

        # Dismiss the "recycled" confirmation panel.
        try:
            close_btn = page.locator(CLOSE_BUTTON_SELECTOR).first
            await close_btn.wait_for(state="visible", timeout=10000)
            await close_btn.click()
        except Exception:
            for frame in page.frames:
                try:
                    fb = frame.locator(CLOSE_BUTTON_SELECTOR).first
                    if await fb.count() > 0:
                        await fb.click()
                        break
                except Exception:
                    continue

        print(f"    {bo_name}: deleted (staged, not published).")
        return "deleted"

    except Exception as e:
        print(f"    {bo_name}: ERROR — {e}")
        return "error"


async def process_env(playwright, env_name: str, creds: dict) -> dict:
    print(f"\n── {env_name} ──")
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()

    dialog_state = {"expected_name": None, "message": None, "accepted": None}
    page.on("dialog", make_dialog_handler(dialog_state))

    result = {"env": env_name, "results": {}}
    try:
        await login(page, creds["base_url"], creds["username"], creds["password"])
        try:
            await page.click("text=Accept All", timeout=3000)
        except Exception:
            pass

        boa_link = page.locator(BOA_LINK_SELECTOR).first
        for attempt in range(3):
            await page.locator(RISE_LINK_SELECTOR).first.click()
            try:
                await boa_link.wait_for(state="visible", timeout=5000)
                break
            except Exception:
                if attempt == 2:
                    raise
                await page.wait_for_timeout(500)
        await boa_link.click()
        await page.wait_for_selector(QUICK_FIND_SELECTOR, timeout=20000)

        for bo_name in TARGET_BOS:
            status = await delete_bo_in_env(page, env_name, bo_name, dialog_state)
            result["results"][bo_name] = status

    except Exception as e:
        print(f"  ❌ Failed to process {env_name}: {e}")
        debug_path = SCREENSHOT_DIR / f"fail_{env_name}.png"
        try:
            await page.screenshot(path=str(debug_path), full_page=True)
            print(f"  Debug screenshot: {debug_path}")
        except Exception:
            pass
        for bo_name in TARGET_BOS:
            result["results"].setdefault(bo_name, "error")

    await browser.close()
    return result


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
            environment_credentials[env_name] = {
                "base_url": base_url, "username": username, "password": password,
            }
        except Exception as e:
            print(f"  FAIL  {env_name}: {e}")

    print(f"Loaded {len(environment_credentials)}/{len(ENV_NAMES)} environments.\n")
    print(f"Target BOs (allowlist): {TARGET_BOS}\n")

    all_results = []
    async with async_playwright() as p:
        for env_name, creds in environment_credentials.items():
            result = await process_env(p, env_name, creds)
            all_results.append(result)

    print("\n\n" + "=" * 60)
    print("SUMMARY (staged deletions — nothing published)")
    print("=" * 60)
    for r in all_results:
        print(f"\n{r['env']}:")
        for bo_name, status in r["results"].items():
            print(f"  {status:12s} {bo_name}")


if __name__ == "__main__":
    asyncio.run(main())
