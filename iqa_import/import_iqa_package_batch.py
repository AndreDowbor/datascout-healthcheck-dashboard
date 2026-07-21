"""
import_iqa_package_batch.py — batch version of import_iqa_package.py: imports
one or more exported IQA folder packages into a target folder (which may be
nested, e.g. $/_DataScout/Segments) across a list of environments.

Context: demo42 (golden) has two subfolders under $/_DataScout/Segments that
are missing from other environments — custom_tag_rules (missing in 24/25
envs) and tag_extension (missing in 4/25 envs, the rest already have their
own tag_extension contents so only need it where the folder is absent).
Packages were exported from demo42 via RiSE > Intelligent Query Architect >
select folder > Export, into iqa_import/packages/.

See iqa_import/README.md for the underlying click path/selectors — this
script only adds multi-level folder tree navigation (the original only
clicks one folder node, assumed to be a direct child of "$").

Usage:
    Edit TARGET_FOLDER_PATH, PACKAGES and ENV_NAMES below, then:
    python3 iqa_import/import_iqa_package_batch.py

Runs with a HEADED browser, one environment at a time. Prints per-env,
per-package result at the end.
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
from common.imis_client import IMISClient

# ── Edit these for each run ─────────────────────────────────────────────────
TARGET_FOLDER_PATH = ["_DataScout", "Segments"]
TARGET_FOLDER_FULL_PATH = "$/_DataScout/Segments/tag_extension"
PACKAGES = [
    REPO_ROOT / "iqa_import" / "packages" / "tag_extension_2026-07-21T07_47_57.xml",
]
# Only the 3 environments confirmed (live check) to be missing tag_extension entirely.
ENV_NAMES = [
    "apimisdemo25", "demosales39", "demosales28",
]
# ─────────────────────────────────────────────────────────────────────────────


async def folder_already_exists(creds: dict) -> bool:
    """Live pre-flight check via the REST API — abort the import for this env
    if TARGET_FOLDER_FULL_PATH already exists, to avoid ever colliding with
    something a client may have created there."""
    client = IMISClient(creds["base_url"], creds["username"], creds["password"])
    docs = client.list_iqas_in_folder("$/_DataScout/Segments")
    paths = {d.get("Path") for d in docs}
    return TARGET_FOLDER_FULL_PATH in paths

RISE_LINK_SELECTOR = "a.RiSELink"
IQA_LINK_SELECTOR = "a[href*='/Staff/AsiCommon/Controls/IQA/Default.aspx']"
FOLDER_NODE_SELECTOR_TMPL = "span.rtIn.TreeNode:text-is('{name}')"
IMPORT_MENU_SELECTOR = "span.rmText:text-is('Import')"
FILE_INPUT_SELECTOR = "#ctl00_TemplateBody_FileUploadfile0"
UPLOAD_BUTTON_SELECTOR = "#ctl00_TemplateBody_UploadButton"
IMPORT_BUTTON_SELECTOR = "#ctl00_TemplateBody_ImportButton"

# Some environments land on the public homepage instead of the staff console
# when navigating to base_url + "/" — go straight to the staff login page instead.
LOGIN_URL_OVERRIDES = {
    "demosales3": "https://demosales3.imiscloud.com/Staff",
}

SCREENSHOT_DIR = REPO_ROOT / "iqa_import" / "screenshots"
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


async def find_frame_with_selector(page, selector: str, timeout: int = 15000):
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


async def import_package(page, package_path: Path) -> str:
    """Returns: 'imported' | 'error'

    NOTE: clicking the final Import button triggers a real form postback that
    reloads the iframe's document. Playwright's click() sometimes never
    resolves across that navigation (the frame execution context goes away
    mid-click). We don't rely on the click() call returning, and we verify
    success via the REST API afterwards (see verify_imported) instead of
    polling the Messages textarea in the (possibly-stale) frame reference.
    """
    try:
        print(f"    {package_path.name}: clicking Import menu...")
        await page.locator(IMPORT_MENU_SELECTOR).first.click(timeout=10000)
        await page.wait_for_timeout(1500)

        file_frame = await find_frame_with_selector(page, FILE_INPUT_SELECTOR)
        if file_frame is None:
            print(f"    {package_path.name}: file input never appeared.")
            return "error"

        print(f"    {package_path.name}: uploading file...")
        await file_frame.locator(FILE_INPUT_SELECTOR).set_input_files(str(package_path))
        await file_frame.locator(UPLOAD_BUTTON_SELECTOR).click()
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        print(f"    {package_path.name}: clicking final Import button (may not return — that's expected)...")
        try:
            await file_frame.locator(IMPORT_BUTTON_SELECTOR).click(timeout=8000)
        except Exception as e:
            print(f"    {package_path.name}: click() didn't confirm ({type(e).__name__}) — proceeding, will verify via API.")

        print(f"    {package_path.name}: waiting for the postback to settle...")
        await page.wait_for_timeout(6000)
        return "imported"
    except Exception as e:
        print(f"    {package_path.name}: ERROR — {e}")
        return "error"


def verify_imported(creds: dict) -> bool:
    """Confirm via the REST API that TARGET_FOLDER_FULL_PATH now exists."""
    client = IMISClient(creds["base_url"], creds["username"], creds["password"])
    docs = client.list_iqas_in_folder("$/_DataScout/Segments")
    paths = {d.get("Path") for d in docs}
    return TARGET_FOLDER_FULL_PATH in paths


async def process_env(playwright, env_name: str, creds: dict) -> dict:
    print(f"\n── {env_name} ──")
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()
    page.on("dialog", lambda d: asyncio.create_task(d.accept()))

    result = {"env": env_name, "results": {}}
    try:
        if await folder_already_exists(creds):
            print(f"  ⛔ SAFETY ABORT: {TARGET_FOLDER_FULL_PATH} already exists in {env_name} — skipping entirely, nothing touched.")
            for pkg in PACKAGES:
                result["results"][pkg.name] = "aborted_already_exists"
            await browser.close()
            return result

        print("  logging in...")
        await login(page, creds["base_url"], creds["username"], creds["password"],
                    login_url=LOGIN_URL_OVERRIDES.get(env_name))
        print("  logged in, navigating to folder...")
        await goto_folder(page, TARGET_FOLDER_PATH)
        print("  in folder, importing...")

        for pkg in PACKAGES:
            status = await import_package(page, pkg)
            if status == "imported":
                verified = verify_imported(creds)
                status = "verified" if verified else "click_ok_but_not_found"
                print(f"    {pkg.name}: post-import verification via API = {verified}")
            result["results"][pkg.name] = status

    except Exception as e:
        print(f"  ❌ Failed to process {env_name}: {e}")
        debug_path = SCREENSHOT_DIR / f"fail_batch_{env_name}.png"
        try:
            await page.screenshot(path=str(debug_path), full_page=True)
            print(f"  Debug screenshot: {debug_path}")
        except Exception:
            pass
        for pkg in PACKAGES:
            result["results"].setdefault(pkg.name, "error")

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

    print(f"Loaded {len(environment_credentials)}/{len(ENV_NAMES)} environments.")
    print(f"Target folder: {'/'.join(TARGET_FOLDER_PATH)}")
    print(f"Packages: {[p.name for p in PACKAGES]}\n")

    all_results = []
    async with async_playwright() as p:
        for env_name, creds in environment_credentials.items():
            result = await process_env(p, env_name, creds)
            all_results.append(result)

    print("\n\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for r in all_results:
        print(f"\n{r['env']}:")
        for pkg_name, status in r["results"].items():
            print(f"  {status:12s} {pkg_name}")


if __name__ == "__main__":
    asyncio.run(main())
