# imis_env_tester_with_1password.py
# IMIS Environment Tester with 1Password, login + click Datascout Profile + refresh + click again + viewport screenshot
# Author: Code GPT

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pyotp
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from supabase import create_client
from onepassword_manager import OnePasswordManager

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

# =============================
#CONFIGURATION  "imis104",
#=============================
ENVIRONMENTS = [
        "i8vdemo13", "isgdemo106", "demo83", "imis87", "atdemo81", "armdemo96", "imis36", "demo86", "atsdemo89",
        "imisdemo11", "ensyncdemo13", "ibcdemo80", "demo42", "atdemo2", "demosales3", "apimisdemo25", "demosales50",
        "aaae", "bsidemo27", "isgdemo14", "oasw", "cpanb", "aboncle",
        "demosales44", "demosales33", "atsdemo90",
   ]

#ENVIRONMENTS = ["imis36"]  # Solo Testing

PROFILE_URLS = {
    "demo83": "https://demoaisp83.imiscloud.com/Shared_Content/Datascout/new_Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "imis87": "https://demosales87.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "atdemo81": "https://demoaisp81.imiscloud.com/Shared_Content/Datascout/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "armdemo96": "https://demoaisp96.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "imis36": "https://demosales36.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "imis104": "https://demosales104.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "imis34": "https://demosales34.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "demo86": "https://demoaisp86.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "atsdemo89": "https://demoaisp89.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "imisdemo11": "https://demosales11.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "ensyncdemo13": "https://demoaisp13.imiscloud.com/Sandbox/Contacts/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "apimisdemo25": "https://apdemosales25.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "ibcdemo80": "https://demoaisp80.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "atdemo2": "https://demoaisp2.imiscloud.com/Shared_Content/Datascout/Account_Staff.aspx?ID=23242&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "demo42": "https://demoaisp42.imiscloud.com/Shared_Content/Datascout/Account_Page_Staff.aspx?ID=21364&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "demosales3": "https://demosales3.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "isgdemo106": "https://demoaisp106.imiscloud.com/MyStaff/ContactManagement/Individuals/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "demosales50": "https://demosales50.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=23337&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "isgdemo106": "https://demoaisp106.imiscloud.com/MyStaff/ContactManagement/Individuals/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "i8vdemo13": "https://apdemoaisp13.imiscloud.com/Shared_Content/Datascout/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "aboncle": "https://abo-ncle.org/Shared_Content/Staff/ContactLayouts/Account_Page_Staff.aspx?ID=269409&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "isgdemo14": "https://demoaisp14.imiscloud.com/MyStaff/ContactManagement/Individuals/Account_Page_Staff.aspx?ID=19734&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "oasw": "https://oasw.org/OASW_Staff/ContactLayouts/Account_Page_Staff.aspx?ID=29263&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "cpanb": "https://staff.cpanewbrunswick.ca/CPASTAFF/ContactLayouts/Account_Page_Staff.aspx?ID=36745&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "bsidemo27": "https://demoaisp27.imiscloud.com/Union-Demo/Workers/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "aaae": "https://member.aaae.org/AAAECore/Contacts/EMS/ContactLayouts/Account_Page_Staff.aspx?ID=303528&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "demosales44": "https://demosales44.imiscloud.com/_Demo/Account-Pages/ContactLayouts/Account_Page_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "demosales33": "https://demosales33.imiscloud.com/Shared_Content/Contacts/OrganizationLayouts/Account_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
    "atsdemo90": "https://demoaisp90.imiscloud.com/_Demo/Account-Pages/ContactLayouts/CAR_Full_Account_Staff.aspx?ID=126&WebsiteKey=4243d9e2-e91e-468c-97c2-2046d70c1e1a",
}

# Environments where the profile URL is on a different domain than the 1Password base URL.
# For these, we navigate to the profile URL directly and let the site redirect us to login.
CROSS_DOMAIN_ENVS = {"oasw", "cpanb", "aboncle", "aaae"}

# Override base login URLs (only used for non-cross-domain envs)
LOGIN_URL_OVERRIDES = {}

USERNAME_SELECTOR = "[id$='signInUserName']"
PASSWORD_SELECTOR = "[id$='signInPassword']"
LOGIN_BUTTON_SELECTOR = "[id$='SubmitButton']"

# Newer iMIS "email first" sign-in widget (currently seen on i8vdemo13).
# Step 1: fill email, click Continue. Step 2: expand "Sign in using iMIS password",
# fill password, click Sign In.
NEW_LOGIN_USERNAME_SELECTOR = "[id$='OpenIdUserName']"
NEW_LOGIN_CONTINUE_SELECTOR = "[id$='OpenIdSubmitButton']"
NEW_LOGIN_PASSWORD_TOGGLE_SELECTOR = "text=Sign in using iMIS password"
NEW_LOGIN_PASSWORD_SELECTOR = "[id$='OpenIdPassword']"
NEW_LOGIN_SIGNIN_SELECTOR = "[id$='ReservedUserSubmitButton']"

PAGE_READY_SELECTOR = "body"
DATASCOUT_BUTTON = "#openBtn"
DATASCOUT_PANEL = "#datascout-profile-panel"  # optional, update if known

OUTPUT_DIR = Path("auth_states")
OUTPUT_DIR.mkdir(exist_ok=True)

SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

RESULTS_FILE = "test_results.json"
HEADLESS = True

# =============================
# HELPERS
# =============================

def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def normalize_base_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


async def safe_goto(page, url: str, label: str = "", timeout_ms: int = 60000, retries: int = 2, wait_until: str = "domcontentloaded"):
    last_err = None
    for attempt in range(retries + 1):
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return
        except Exception as e:
            last_err = e
            msg = str(e)
            print(f"Navigation error{(' for ' + label) if label else ''} (attempt {attempt + 1}/{retries + 1}): {msg}")

            if "net::ERR_ABORTED" in msg or "Navigation failed" in msg or "Timeout" in msg:
                await page.wait_for_timeout(1200)
                continue

            raise

    raise last_err


async def wait_post_login(page):
    try:
        await page.wait_for_selector(USERNAME_SELECTOR, state="detached", timeout=20000)
        return
    except Exception:
        await page.wait_for_selector(PAGE_READY_SELECTOR, timeout=20000)


# =============================
# CORE LOGIC
# =============================

async def login_and_open_datascout_profile(playwright, env_name, base_url, username, password, target_url):
    """
    Logs into IMIS, opens staff page, clicks Datascout Profile, refreshes, clicks again.
    Screenshot removed here so we only get ONE screenshot per env (the retest screenshot after refresh).
    """
    browser = await playwright.chromium.launch(headless=HEADLESS)
    context = await browser.new_context()
    page = await context.new_page()

    base_url = normalize_base_url(base_url)
    login_url = f"{base_url}/"

    print(f"\nLogging into {env_name} at {login_url}...")
    await safe_goto(page, login_url, label=f"{env_name} login", wait_until="load")

    # If login form isn't present, the site redirected to its homepage — click Sign In
    login_form_visible = False
    use_new_login = False
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
        print(f"{env_name}: Login form not on root page (URL: {page.url}), looking for Sign In link...")
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
                    print(f"{env_name}: Clicked sign-in link ({sel}), waiting for login form...")
                    login_form_visible = True
                    break
            except Exception:
                continue

    if not login_form_visible:
        debug_path = SCREENSHOT_DIR / f"{env_name.lower()}_login_debug_{timestamp()}.png"
        await page.screenshot(path=str(debug_path), full_page=True)
        print(f"No login form or Sign In link found. Debug screenshot saved: {debug_path}")
        print(f"Current URL: {page.url}")
        raise RuntimeError(f"Could not reach login form for {env_name}")

    if use_new_login:
        try:
            await page.fill(NEW_LOGIN_USERNAME_SELECTOR, username)
            await page.click(NEW_LOGIN_CONTINUE_SELECTOR)
            await page.click(NEW_LOGIN_PASSWORD_TOGGLE_SELECTOR, timeout=8000)
            await page.wait_for_selector(NEW_LOGIN_PASSWORD_SELECTOR, state="visible", timeout=8000)
            await page.fill(NEW_LOGIN_PASSWORD_SELECTOR, password)
            await page.click(NEW_LOGIN_SIGNIN_SELECTOR)
        except Exception:
            debug_path = SCREENSHOT_DIR / f"{env_name.lower()}_login_debug_{timestamp()}.png"
            await page.screenshot(path=str(debug_path), full_page=True)
            print(f"New-style login flow failed. Debug screenshot saved: {debug_path}")
            print(f"Current URL: {page.url}")
            raise
    else:
        try:
            await page.wait_for_selector(USERNAME_SELECTOR, timeout=20000)
        except Exception:
            debug_path = SCREENSHOT_DIR / f"{env_name.lower()}_login_debug_{timestamp()}.png"
            await page.screenshot(path=str(debug_path), full_page=True)
            print(f"Login form still not found after Sign In click. Debug screenshot saved: {debug_path}")
            print(f"Current URL: {page.url}")
            raise

        await page.fill(USERNAME_SELECTOR, username)
        await page.fill(PASSWORD_SELECTOR, password)
        await page.click(LOGIN_BUTTON_SELECTOR)

    await wait_post_login(page)
    print(f"{env_name}: Logged in successfully.")

    print(f"Navigating to staff profile page for {env_name}...")
    await safe_goto(page, target_url, label=f"{env_name} staff page")

    await page.wait_for_selector(PAGE_READY_SELECTOR, timeout=20000)
    print(f"Staff page loaded successfully for {env_name}.")

    print("Clicking 'Datascout Profile' button (first time)...")
    try:
        await page.wait_for_selector(DATASCOUT_BUTTON, timeout=20000)
    except Exception:
        debug_path = SCREENSHOT_DIR / f"{env_name.lower()}_datascout_debug_{timestamp()}.png"
        await page.screenshot(path=str(debug_path), full_page=True)
        print(f"Datascout button (#openBtn) not found. Debug screenshot saved: {debug_path}")
        print(f"Current URL: {page.url}")
        raise
    await page.click(DATASCOUT_BUTTON)
    print("First click successful.")

    try:
        await page.wait_for_selector(DATASCOUT_PANEL, timeout=8000)
        print("Datascout Profile panel detected.")
    except Exception:
        print("Datascout panel not detected (may be expected depending on behavior).")

    print("Refreshing the page...")
    await page.reload(wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_selector(DATASCOUT_BUTTON, timeout=20000)
    print("Page reloaded successfully.")

    print("Clicking 'Datascout Profile' button (after refresh)...")
    await page.click(DATASCOUT_BUTTON)
    print("Second click successful.")

    print("Waiting 10 seconds for Datascout panel to load fully...")
    await asyncio.sleep(10)

    state_path = OUTPUT_DIR / f"{env_name.lower()}_auth.json"
    await context.storage_state(path=state_path)

    await browser.close()
    return state_path


def _resolve_otp(otp_value: str) -> str:
    """Convert an otpauth:// URI or raw secret to the current 6-digit TOTP code."""
    if otp_value.startswith("otpauth://"):
        totp = pyotp.parse_uri(otp_value)
    else:
        totp = pyotp.TOTP(otp_value)
    return totp.now()


async def login_via_redirect(playwright, env_name, username, password, target_url, otp=None):
    """
    For cross-domain environments (e.g. oasw.org, staff.cpanewbrunswick.ca):
    navigate directly to the profile URL. The site redirects to its login page
    on the same domain. After login the session cookie is valid for that domain.
    """
    browser = await playwright.chromium.launch(headless=HEADLESS)
    context = await browser.new_context()
    page = await context.new_page()

    print(f"\n[cross-domain] Navigating directly to profile URL for {env_name}: {target_url}")
    await safe_goto(page, target_url, label=f"{env_name} profile direct", wait_until="load")

    # Wait for the login redirect — form should appear on the same domain as target_url
    login_form_visible = False
    try:
        await page.wait_for_selector(USERNAME_SELECTOR, timeout=15000)
        login_form_visible = True
        print(f"{env_name}: Redirected to login form at {page.url}")
    except Exception:
        print(f"{env_name}: No immediate login form, looking for Sign In link at {page.url}...")
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
                    await page.wait_for_selector(USERNAME_SELECTOR, timeout=15000)
                    login_form_visible = True
                    print(f"{env_name}: Clicked sign-in link ({sel})")
                    break
            except Exception:
                continue

    if not login_form_visible:
        debug_path = SCREENSHOT_DIR / f"{env_name.lower()}_crossdomain_debug_{timestamp()}.png"
        await page.screenshot(path=str(debug_path), full_page=True)
        print(f"No login form found via redirect. Debug screenshot: {debug_path}")
        print(f"Current URL: {page.url}")
        raise RuntimeError(f"Cross-domain login redirect failed for {env_name}")

    await page.fill(USERNAME_SELECTOR, username)
    await page.fill(PASSWORD_SELECTOR, password)
    await page.click(LOGIN_BUTTON_SELECTOR)

    # Some portals show a second "Security code" / TOTP step after username+password submit
    SECOND_FACTOR_SELECTOR = "[id$='SecondFactor']"
    if otp:
        try:
            await page.wait_for_selector(SECOND_FACTOR_SELECTOR, timeout=8000)
            totp_code = _resolve_otp(otp)
            await page.fill(SECOND_FACTOR_SELECTOR, totp_code)
            print(f"{env_name}: Security code (TOTP) filled.")
            await page.click(LOGIN_BUTTON_SELECTOR)
        except Exception:
            pass  # No second factor field — single-step login

    await wait_post_login(page)
    print(f"{env_name}: Logged in via redirect successfully.")

    # Navigate to profile page explicitly (in case post-login landed elsewhere)
    print(f"Navigating to staff profile page for {env_name}...")
    await safe_goto(page, target_url, label=f"{env_name} staff page post-login")
    await page.wait_for_selector(PAGE_READY_SELECTOR, timeout=20000)
    print(f"Staff page loaded for {env_name}.")

    print("Clicking 'Datascout Profile' button (first time)...")
    try:
        await page.wait_for_selector(DATASCOUT_BUTTON, timeout=20000)
    except Exception:
        debug_path = SCREENSHOT_DIR / f"{env_name.lower()}_datascout_debug_{timestamp()}.png"
        await page.screenshot(path=str(debug_path), full_page=True)
        print(f"Datascout button (#openBtn) not found. Debug screenshot saved: {debug_path}")
        print(f"Current URL: {page.url}")
        raise
    await page.click(DATASCOUT_BUTTON)
    print("First click successful.")

    try:
        await page.wait_for_selector(DATASCOUT_PANEL, timeout=8000)
        print("Datascout Profile panel detected.")
    except Exception:
        print("Datascout panel not detected (may be expected).")

    print("Refreshing the page...")
    await page.reload(wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_selector(DATASCOUT_BUTTON, timeout=20000)
    print("Page reloaded successfully.")

    print("Clicking 'Datascout Profile' button (after refresh)...")
    await page.click(DATASCOUT_BUTTON)
    print("Second click successful.")

    print("Waiting 10 seconds for Datascout panel to load fully...")
    await asyncio.sleep(10)

    state_path = OUTPUT_DIR / f"{env_name.lower()}_auth.json"
    await context.storage_state(path=state_path)
    await browser.close()
    return state_path


async def test_datascout_profile(playwright, env_name, target_url, auth_state_path):
    """
    Re-tests the Datascout click sequence using saved session.
    This is the ONLY place we take a screenshot now (after refresh/reload).
    """
    browser = await playwright.chromium.launch(headless=HEADLESS)
    context = await browser.new_context(storage_state=str(auth_state_path))
    page = await context.new_page()

    result = {"env": env_name, "url": target_url}
    start_time = time.time()

    try:
        await safe_goto(page, target_url, label=f"{env_name} retest staff page")

        await page.wait_for_selector(DATASCOUT_BUTTON, timeout=20000)
        await page.click(DATASCOUT_BUTTON)

        await page.reload(wait_until="domcontentloaded", timeout=60000)

        await page.wait_for_selector(DATASCOUT_BUTTON, timeout=20000)
        await page.click(DATASCOUT_BUTTON)

        await asyncio.sleep(10)

        ts = timestamp()
        screenshot_path = SCREENSHOT_DIR / f"{env_name.lower()}_profile_panel_retest_{ts}.png"
        await page.screenshot(path=str(screenshot_path))
        print(f"Viewport screenshot (retest) saved: {screenshot_path}")

        elapsed = round(time.time() - start_time, 2)
        result.update({"status": "PASS", "time": f"{elapsed}s"})
    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        result.update({"status": "FAIL", "error": str(e), "time": f"{elapsed}s"})

    await browser.close()
    return result


# =============================
# MAIN RUNNER
# =============================

async def main():
    print("Initializing 1Password client...")
    op = OnePasswordManager()
    results = []

    async with async_playwright() as p:
        for env_name in ENVIRONMENTS:
            print(f"\nFetching credentials for {env_name} from 1Password...")
            try:
                creds = await op.get_flattened_client_item(env_name)
                print("1Password fields returned:", creds.keys())

                username = creds.get("imis_user") or creds.get("username") or creds.get("user")
                password = creds.get("imis_password") or creds.get("password")
                base_url = creds.get("imis_base_url") or creds.get("base_url") or creds.get("imis_url")

                target_url = PROFILE_URLS.get(env_name)
                if not target_url:
                    raise ValueError(f"Missing profile URL for {env_name}")

                if env_name in CROSS_DOMAIN_ENVS:
                    if not all([username, password]):
                        missing = [k for k, v in {"username": username, "password": password}.items() if not v]
                        raise ValueError(f"Missing credentials: {missing}")
                else:
                    if not all([username, password, base_url]):
                        missing = [k for k, v in {"username": username, "password": password, "base_url": base_url}.items() if not v]
                        raise ValueError(f"Missing credentials: {missing}")

                for attempt in range(2):
                    try:
                        if env_name in CROSS_DOMAIN_ENVS:
                            otp = creds.get("one-time_password") or creds.get("one_time_password") or creds.get("otp")
                            state_path = await login_via_redirect(p, env_name, username, password, target_url, otp=otp)
                        else:
                            base_url = LOGIN_URL_OVERRIDES.get(env_name, base_url)
                            state_path = await login_and_open_datascout_profile(p, env_name, base_url, username, password, target_url)
                        res = await test_datascout_profile(p, env_name, target_url, state_path)
                        break
                    except Exception as e:
                        if attempt == 0:
                            print(f"{env_name}: attempt 1 failed ({e}), retrying in 10s...")
                            await asyncio.sleep(10)
                        else:
                            raise

            except Exception as e:
                print(f"{env_name}: FAIL — {e}")
                res = {"env": env_name, "url": PROFILE_URLS.get(env_name, ""), "status": "FAIL", "error": str(e), "time": "0s"}

            results.append(res)
            print(f"{env_name}: {res['status']} ({res['time']})")
            if res["status"] == "FAIL":
                print(f"Error: {res['error']}")

    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)

    print("All tests complete. Results saved to:", RESULTS_FILE)

    # Push results to Supabase
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if url and key:
        checked_at = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "environment": r.get("env"),
                "url": r.get("url"),
                "status": r.get("status", "FAIL"),
                "duration_seconds": float(r.get("time", "0s").replace("s", "")),
                "error": r.get("error"),
                "checked_at": checked_at,
            }
            for r in results
        ]
        try:
            supabase = create_client(url, key)
            supabase.table("profile_checks").insert(rows).execute()
            print(f"  → Pushed {len(rows)} profile results to Supabase.")
        except Exception as exc:
            print(f"  [warn] Supabase push failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
