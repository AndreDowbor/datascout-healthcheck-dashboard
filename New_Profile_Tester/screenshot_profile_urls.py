# screenshot_profile_urls.py — visit the profiles.staging.app.datascout.ai
# URL for each environment, logging into iMIS first when needed (reusing the
# real login flow so the SSO session cookie is actually set), then screenshot
# the profile page. Screenshots go in profile_url_screenshots/, one per env.
#
# Usage:
#   python3 screenshot_profile_urls.py                 # all known environments
#   python3 screenshot_profile_urls.py demo42 atdemo2   # just these
#   python3 screenshot_profile_urls.py --direct         # open the profile URL
#                                                        # directly (no staff page,
#                                                        # no button click), log in
#                                                        # on whatever page it lands
#                                                        # on, wait 10s, one screenshot
#   python3 screenshot_profile_urls.py --direct demo42 atdemo2   # just these

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

from playwright.async_api import async_playwright
from onepassword_manager import OnePasswordManager

import imis_env_tester_with_1password as tester

OUT_DIR = Path("profile_url_screenshots")
OUT_DIR.mkdir(exist_ok=True)

PROFILE_URL_TEMPLATE = "https://profiles.staging.app.datascout.ai/{client_id}/profile/126"

# Environments we have working 1Password creds + a real staff-page login flow
# for (same set validated in today's Profile Tester runs).
DEFAULT_ENVIRONMENTS = list(tester.ENVIRONMENTS) + ["imis104"]

# The 26 core client_ids (IQA/Profile healthcheck set) — used by --no-login
# mode, which doesn't need 1Password creds at all since it never logs in.
ALL_CLIENT_IDS_FROM_SHEET = [
    "bsidemo27", "armdemo96", "atdemo2", "atdemo81", "atsdemo89", "atsdemo90",
    "ensyncdemo13", "i8vdemo13", "ibcdemo80", "imis104", "imis87", "isgdemo106",
    "isgdemo14", "demo42", "demo86", "demo83", "apimisdemo25", "demosales3",
    "demosales33", "demosales39", "demosales50", "imis36", "imisdemo11",
    "demosales28", "demo14", "demosales44",
]


async def run_one(playwright, op, env_name: str):
    result = {"env": env_name}
    try:
        creds = await op.get_flattened_client_item(env_name)
        username = creds.get("imis_user") or creds.get("username") or creds.get("user")
        password = creds.get("imis_password") or creds.get("password")
        base_url = creds.get("imis_base_url") or creds.get("base_url") or creds.get("imis_url")
        staff_target_url = tester.PROFILE_URLS.get(env_name)

        if not staff_target_url or not all([username, password, base_url]):
            result.update({"status": "SKIP", "error": "Missing creds or staff URL"})
            return result

        # Establish a real session (login + open the Datascout button once)
        # so the hidden SSO iframe sets the profiles.staging cookie, exactly
        # like a real user would trigger it. iMIS sessions here drop
        # intermittently (same flakiness seen all day in the Profile Tester
        # runs), so retry once like main() does.
        state_path = tester.OUTPUT_DIR / f"{env_name.lower()}_auth.json"
        for attempt in range(2):
            try:
                if env_name in tester.CROSS_DOMAIN_ENVS:
                    otp = creds.get("one-time_password") or creds.get("one_time_password") or creds.get("otp")
                    await tester.login_via_redirect(playwright, env_name, username, password, staff_target_url, otp=otp, save_state_path=state_path)
                else:
                    base_url_eff = tester.LOGIN_URL_OVERRIDES.get(env_name, base_url)
                    await tester.login_and_open_datascout_profile(playwright, env_name, base_url_eff, username, password, staff_target_url, save_state_path=state_path)
                break
            except Exception as e:
                if attempt == 0:
                    print(f"[{env_name}] login attempt 1 failed ({e}), retrying in 10s...")
                    await asyncio.sleep(10)
                else:
                    raise

        # Reopen with the saved session and go straight to the profiles URL.
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=str(state_path))
        page = await context.new_page()

        profile_url = PROFILE_URL_TEMPLATE.format(client_id=env_name)
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(10000)

        screenshot_path = OUT_DIR / f"{env_name}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        await browser.close()

        result.update({"status": "OK", "screenshot": str(screenshot_path), "url": profile_url})
    except Exception as e:
        result.update({"status": "FAIL", "error": str(e)})
    return result


async def run_direct_login_sweep(playwright, op, client_ids: list[str]):
    """
    Open the profiles.staging URL directly (no iMIS staff page, no button
    click, no reload dance). If that redirects to a login form — classic or
    the newer OpenID-style widget — log in right there with the client's own
    1Password credentials. Wait 10s, one screenshot, done. Fresh browser
    context per client_id so no session/cookie bleeds from one client into
    the next (that cross-client session bleed was a real bug we found
    earlier today).
    """
    out_dir = OUT_DIR.parent / "profile_url_screenshots_direct"
    out_dir.mkdir(exist_ok=True)
    print(f"Sweeping {len(client_ids)} client_ids -> {out_dir}/ (direct URL, login if needed)")

    for client_id in client_ids:
        url = PROFILE_URL_TEMPLATE.format(client_id=client_id)
        print(f"\n[{client_id}] -> {url}")
        browser = await playwright.chromium.launch(headless=False)
        page = await (await browser.new_context()).new_page()
        try:
            creds = await op.get_flattened_client_item(client_id)
            username = creds.get("imis_user") or creds.get("username") or creds.get("user")
            password = creds.get("imis_password") or creds.get("password")

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            login_form_visible = False
            use_new_login = False
            try:
                await page.wait_for_selector(tester.USERNAME_SELECTOR, timeout=8000)
                login_form_visible = True
            except Exception:
                try:
                    await page.wait_for_selector(tester.NEW_LOGIN_USERNAME_SELECTOR, timeout=5000)
                    login_form_visible = True
                    use_new_login = True
                except Exception:
                    pass

            if login_form_visible and username and password:
                print(f"[{client_id}] login form found, logging in...")
                if use_new_login:
                    await page.fill(tester.NEW_LOGIN_USERNAME_SELECTOR, username)
                    await page.click(tester.NEW_LOGIN_CONTINUE_SELECTOR)
                    await page.click(tester.NEW_LOGIN_PASSWORD_TOGGLE_SELECTOR, timeout=8000)
                    await page.wait_for_selector(tester.NEW_LOGIN_PASSWORD_SELECTOR, state="visible", timeout=8000)
                    await page.fill(tester.NEW_LOGIN_PASSWORD_SELECTOR, password)
                    await page.click(tester.NEW_LOGIN_SIGNIN_SELECTOR)
                else:
                    await page.fill(tester.USERNAME_SELECTOR, username)
                    await page.fill(tester.PASSWORD_SELECTOR, password)
                    await page.click(tester.LOGIN_BUTTON_SELECTOR)
            elif login_form_visible:
                print(f"[{client_id}] login form found but no 1Password creds for this client_id — skipping login")
            else:
                print(f"[{client_id}] no login form appeared — already on profile page or a different state")

            await page.wait_for_timeout(10000)
            ts = tester.timestamp()
            screenshot_path = out_dir / f"{client_id}_{ts}.png"
            await page.screenshot(path=str(screenshot_path))
            print(f"[{client_id}] screenshot saved -> {screenshot_path}")
        except Exception as e:
            print(f"[{client_id}] FAIL — {e}")
        finally:
            await browser.close()


async def main():
    args = sys.argv[1:]
    op = OnePasswordManager()

    if "--direct" in args:
        client_ids = [a for a in args if a != "--direct"] or ALL_CLIENT_IDS_FROM_SHEET
        async with async_playwright() as p:
            await run_direct_login_sweep(p, op, client_ids)
        return

    envs = args or DEFAULT_ENVIRONMENTS
    print(f"Screenshotting {len(envs)} environments -> {OUT_DIR}/")

    async with async_playwright() as p:
        for env_name in envs:
            print(f"\n[{env_name}] logging in + capturing profile page...")
            res = await run_one(p, op, env_name)
            print(f"[{env_name}] {res['status']}" + (f" — {res.get('error')}" if res.get("error") else f" -> {res.get('screenshot')}"))


if __name__ == "__main__":
    asyncio.run(main())
