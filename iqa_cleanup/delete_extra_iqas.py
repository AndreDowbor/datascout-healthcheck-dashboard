"""
delete_extra_iqas.py — stages deletion (Organize > Delete) of the 9 known
systemic legacy IQAs across environments, via the RiSE Intelligent Query
Architect UI (there's no REST API for this).

demo42 is the golden environment. These 9 IQAs exist in 25/25 non-golden
environments but not in demo42 (confirmed by healthcheck/iqa_healthcheck.py
Section 4 — extra_iqas_report_20260720.xlsx), so they're being removed
everywhere else to match golden. Same pattern/precedent as bo_cleanup.

SAFETY — read before running:
  - TARGET_ITEMS is a hardcoded allowlist (folder + name). Nothing outside
    these exact items is ever touched.
  - Before confirming a delete, the script checks that the browser's native
    confirm() dialog message actually contains the target item's name. If
    it doesn't match, the dialog is dismissed (Cancel) and that item is
    skipped instead of proceeding blind.
  - This only STAGES the deletion (Organize > Delete > OK). It moves the
    item to the Recycle Bin and marks it "Working" (draft) — Publish is
    NEVER clicked by this script. The live system is unaffected until
    someone explicitly publishes.
  - If a target item isn't found in an environment (already deleted, or
    never existed there), it's skipped and logged — not an error.

Usage:
    python3 iqa_cleanup/delete_extra_iqas.py
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
# (folder path under $/_DataScout, item name)
TARGET_ITEMS = [
    (["_DataScout", "AiParts", "Profile"], "tags_by_id"),
]

ENV_NAMES = [
    "demosales28",
]

# Some environments land on the public homepage instead of the staff console
# when navigating to base_url + "/" — go straight to the staff login page instead.
LOGIN_URL_OVERRIDES = {
    "demosales3": "https://demosales3.imiscloud.com/Staff",
}

RISE_LINK_SELECTOR = "a.RiSELink"
IQA_LINK_SELECTOR = "a[href*='/Staff/AsiCommon/Controls/IQA/Default.aspx']"
FOLDER_NODE_SELECTOR_TMPL = "span.rtIn.TreeNode:text-is('{name}')"
ORGANIZE_MENU_SELECTOR = "span.rmText.rmExpandDown:text-is('Organize')"
DELETE_MENU_SELECTOR = "span.rmText:text-is('Delete')"
CLOSE_BUTTON_SELECTOR = "#ctl00_CancelButton"

SCREENSHOT_DIR = REPO_ROOT / "iqa_cleanup" / "screenshots"
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


async def goto_folder(page, folder_parts):
    await page.wait_for_timeout(600)
    await page.locator(RISE_LINK_SELECTOR).first.click()
    iqa_link = page.locator(IQA_LINK_SELECTOR).first
    for attempt in range(5):
        try:
            await iqa_link.wait_for(state="visible", timeout=5000)
            break
        except Exception:
            if attempt == 4:
                raise
            await page.wait_for_timeout(800)
            await page.locator(RISE_LINK_SELECTOR).first.click()
            await page.wait_for_timeout(800)
    await iqa_link.click(timeout=10000)
    await page.wait_for_timeout(1500)
    for name in folder_parts:
        node = page.locator(FOLDER_NODE_SELECTOR_TMPL.format(name=name)).first
        await node.wait_for(state="visible", timeout=10000)
        await node.click()
        await page.wait_for_timeout(1200)


async def delete_item_in_env(page, env_name: str, item_name: str, dialog_state: dict) -> str:
    """Returns: 'deleted' | 'not_found' | 'mismatch' | 'error'"""
    dialog_state["expected_name"] = item_name
    dialog_state["message"] = None
    dialog_state["accepted"] = None

    item_selector = f"span.ObjectBrowserContentListName:has-text('{item_name}')"

    try:
        item_locator = page.locator(item_selector).first
        try:
            await item_locator.wait_for(state="visible", timeout=8000)
        except Exception:
            # Fallback: plain text match (folder listing sometimes uses a
            # different markup than the Business Object Designer).
            item_locator = page.locator(f"text={item_name}").first
            try:
                await item_locator.wait_for(state="visible", timeout=5000)
            except Exception:
                print(f"    {item_name}: not found in {env_name} — skipping.")
                return "not_found"

        await item_locator.click()
        await page.wait_for_timeout(400)

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

        await page.wait_for_timeout(2000)

        if dialog_state["message"] is None:
            print(f"    {item_name}: no confirm dialog appeared — treating as error.")
            return "error"
        if not dialog_state["accepted"]:
            print(f"    {item_name}: dialog message didn't mention the item name — ABORTED for safety.")
            print(f"      Dialog said: {dialog_state['message']}")
            return "mismatch"

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

        print(f"    {item_name}: deleted (staged, not published).")
        return "deleted"

    except Exception as e:
        print(f"    {item_name}: ERROR — {e}")
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
        await login(page, creds["base_url"], creds["username"], creds["password"],
                    login_url=LOGIN_URL_OVERRIDES.get(env_name))

        # Re-navigate to the target folder before EVERY item — a successful
        # delete's "Recycled" confirmation/close can reset the tree view, so
        # we can't assume we're still inside the same folder for the next item.
        for folder_parts, item_name in TARGET_ITEMS:
            await goto_folder(page, folder_parts)
            status = await delete_item_in_env(page, env_name, item_name, dialog_state)
            result["results"][item_name] = status

    except Exception as e:
        print(f"  ❌ Failed to process {env_name}: {e}")
        debug_path = SCREENSHOT_DIR / f"fail_{env_name}.png"
        try:
            await page.screenshot(path=str(debug_path), full_page=True)
            print(f"  Debug screenshot: {debug_path}")
        except Exception:
            pass
        for _, item_name in TARGET_ITEMS:
            result["results"].setdefault(item_name, "error")

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
    print(f"Target items (allowlist): {[name for _, name in TARGET_ITEMS]}\n")

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
        for item_name, status in r["results"].items():
            print(f"  {status:12s} {item_name}")


if __name__ == "__main__":
    asyncio.run(main())
