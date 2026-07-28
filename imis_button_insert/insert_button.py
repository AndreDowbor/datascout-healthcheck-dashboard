"""
insert_button.py — installs the Datascout Concierge chat button on an
environment's "Member Home" page (@/Web/Member Home in iMIS's Page Builder).

Validated end-to-end against armdemo96 on 2026-07-21 (button confirmed live
on the published page while logged in).

One client at a time by design, not a batch loop: folder structure under "@"
varies between environments (e.g. atdemo2 has no top-level "Web" folder at
all — see the diagnostic dump this script prints on failure), so each new
environment should be run and visually confirmed before moving to the next.

Usage:
    python3 insert_button.py <client_id>

Reuses the login() pattern from iqa_rest_fix/fix_rest_availability.py verbatim.
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

# Some environments land on the public homepage instead of the staff console
# when navigating to base_url + "/" — go straight to the staff login page instead.
LOGIN_URL_OVERRIDES = {
    "isgdemo106": "https://demoaisp106.imiscloud.com/staff",
    "isgdemo14": "https://demoaisp14.imiscloud.com/staff",
}

RISE_LINK_SELECTOR = "a.RiSELink"
PAGE_BUILDER_SELECTOR = "a.rtIn:has-text('Page Builder')"
MANAGE_CONTENT_SELECTOR = "a.rtIn:has-text('Manage content')"
WEB_FOLDER_SELECTOR = "span.rtIn.TreeNode:text-is('Web')"
MEMBER_HOME_ITEM_SELECTOR = "span.pl-2:text-is('Member Home')"
EDIT_BUTTON_SELECTOR = "span.rmText:text-is('Edit')"
ADD_CONTENT_LINK_SELECTOR = "#AddContentLink"
CONTENT_HTML_ITEM_SELECTOR = "text='Content Html (shortcut to Content Html)'"
CONTENT_GALLERY_OK_BUTTON_SELECTOR = "#ctl00_OkButton"
CONVERT_TO_ADVANCED_SELECTOR = "#ctl00_TemplateBody_ContentEditorChildControl_ConvertButton"
CONTENT_ITEM_NAME_SELECTOR = "#ctl00_TemplateBody_ContentEditorChildControl_ContentItemName_TextField"
HTML_TAB_SELECTOR = "a[href='#Html'][title='HTML']"
HTML_TEXTAREA_SELECTOR = "textarea.reTextArea"
ITEM_OK_BUTTON_SELECTOR = "input#ctl00_SaveButton[value='OK']"
SAVE_AND_PUBLISH_SELECTOR = "#ctl00_SaveAndCloseButton"

CONTENT_ITEM_NAME = "Datascout Concierge Button"

# The client_key + chat URL below are hardcoded to demo42 in the source
# snippet the user copied from a working install — swapped per-environment
# via string replace before pasting.
_TEMPLATE_CLIENT_ID = "demo42"
BUTTON_HTML_TEMPLATE = r"""<style>
    /* Hide the original back to top button */
    .backToTop {
    display: none !important;
    }
    /* Chatbot bubble styles */
    .chatbot-bubble {
    position: fixed;
    bottom: 30px;
    right: 30px;
    width: 60px;
    height: 60px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 50%;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    .chatbot-bubble:hover {
    transform: scale(1.1);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
    }
    .chatbot-bubble svg {
    width: 32px;
    height: 32px;
    fill: white;
    }
    /* Right-side panel styles */
    .chatbot-panel {
    position: fixed;
    bottom: 0;
    right: -480px;
    width: 480px;
    height: calc(100vh - 100px);
    background: white;
    box-shadow: -2px 0 10px rgba(0, 0, 0, 0.1);
    z-index: 10000;
    transition: right 0.3s ease;
    display: flex;
    flex-direction: column;
    }
    @media (max-width: 768px) {
    .chatbot-panel {
    width: 100%;
    right: -100%;
    height: 100%;
    }
    }
    .chatbot-panel.open {
    right: 0;
    }
    .chatbot-panel-header {
    background: white;
    border-bottom: 1px solid #e5e5e5;
    padding: 12px 16px;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    min-height: 48px;
    }
    .chatbot-close-btn {
    background: transparent;
    border: none;
    color: #999;
    font-size: 24px;
    cursor: pointer;
    padding: 4px;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s;
    border-radius: 4px;
    }
    .chatbot-close-btn:hover {
    color: #333;
    background: #f5f5f5;
    }
    .chatbot-panel-content {
    flex: 1;
    overflow: hidden;
    position: relative;
    }
    .chatbot-panel iframe {
    width: 100%;
    height: 100%;
    border: none;
    display: block;
    }
    /* Loading indicator */
    .chatbot-loading {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
    color: #667eea;
    padding: 20px;
    max-width: 80%;
    }
    .chatbot-loading-error {
    color: #dc3545;
    font-size: 14px;
    margin-top: 10px;
    }
    /* Overlay for mobile */
    .chatbot-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    z-index: 9998;
    display: none;
    transition: opacity 0.3s ease;
    }
    .chatbot-overlay.active {
    display: block;
    }
    /* Responsive styles */
    @media (max-width: 768px) {
    .chatbot-panel {
    width: 100%;
    right: -100%;
    }
    .chatbot-bubble {
    bottom: 20px;
    right: 20px;
    width: 56px;
    height: 56px;
    }
    }
    /* Hidden SSO iframe */
    #ssoSetupFrame {
    display: none;
    width: 0;
    height: 0;
    border: none;
    }
</style>
<!-- Hidden SSO iframe (loads session cookie) -->
<iframe id="ssoSetupFrame"></iframe>
<!-- Chatbot bubble -->
<div class="chatbot-bubble" id="chatbotBubble">
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
<path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"></path>
<circle cx="12" cy="10" r="1.5"></circle>
<circle cx="8" cy="10" r="1.5"></circle>
<circle cx="16" cy="10" r="1.5"></circle>
</svg>
</div>
<!-- Overlay -->
<div class="chatbot-overlay" id="chatbotOverlay"></div>
<!-- Right-side panel -->
<div class="chatbot-panel" id="chatbotPanel">
<div class="chatbot-panel-header">
<button type="button" class="chatbot-close-btn" id="chatbotCloseBtn">×</button>
</div>
<div class="chatbot-panel-content">
<div class="chatbot-loading" id="chatbotLoading">
<div>Loading chatbot...</div>
<div class="chatbot-loading-error" id="chatbotError" style="display:none;"></div>
</div>
<iframe id="chatbotIframe" allow="microphone; camera"></iframe>
</div>
</div>
<script>
(function() {

    client_key = "demo42";

    console.log('[Chatbot] Initializing...');

    const SSO_URL = '/Shared_Content/Datascout/DatascoutSSOStaging.aspx';
    const ssoSetupFrame = document.getElementById('ssoSetupFrame');

    // Make sure the hidden SSO iframe has the correct URL
    ssoSetupFrame.src = SSO_URL;

    let ssoReady = false;

    // Once the hidden SSO iframe finishes loading, we can set the profile iframe
    ssoSetupFrame.addEventListener('load', function() {
        console.log('[Parent] Hidden SSO iframe loaded. Session cookie should be set.');

        // Get logged in party ID
        const context = getClientContext();
        const loggedInPartyId = context.loggedInPartyId || '';

        console.log('[Chatbot] Extracted loggedInPartyId:', loggedInPartyId);
        console.log('[Chatbot] SSO ready - user can now open chatbot');

        ssoReady = true;
    });

    // Get client context data
    function getClientContext() {
        try {
            const paramElement = document.getElementById('__ClientContext');
            console.log('[Chatbot] Looking for __ClientContext element:', paramElement);

            if (!paramElement) {
                console.warn('[Chatbot] __ClientContext element not found');
                return {};
            }

            const jsonString = paramElement.getAttribute('value');
            console.log('[Chatbot] Raw JSON string:', jsonString);

            if (!jsonString) {
                console.warn('[Chatbot] __ClientContext value is empty');
                return {};
            }

            const parsed = JSON.parse(jsonString);
            console.log('[Chatbot] Parsed context:', parsed);
            return parsed;
        } catch (error) {
            console.error('[Chatbot] Error parsing client context:', error);
            return {};
        }
    }

    // Get elements
    const bubble = document.getElementById('chatbotBubble');
    const panel = document.getElementById('chatbotPanel');
    const overlay = document.getElementById('chatbotOverlay');
    const closeBtn = document.getElementById('chatbotCloseBtn');
    const iframe = document.getElementById('chatbotIframe');
    const loading = document.getElementById('chatbotLoading');
    const errorDiv = document.getElementById('chatbotError');

    console.log('[Chatbot] Elements found:', {
        bubble: !!bubble,
        panel: !!panel,
        overlay: !!overlay,
        closeBtn: !!closeBtn,
        iframe: !!iframe,
        loading: !!loading,
        errorDiv: !!errorDiv
    });

    let iframeLoaded = false;
    let loadTimeout = null;

    // Build chatbot URL
    const chatbotUrl = 'https://engage.staging.app.datascout.ai/demo42/chat'

    console.log('[Chatbot] Generated URL:', chatbotUrl);

    // Open panel
    function openPanel(e) {
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }

        console.log('[Chatbot] Open panel requested...');

        // Check if SSO is ready before loading chatbot
        if (!ssoReady) {
            console.log('[Chatbot] SSO not ready yet, please wait...');
            if (loading && errorDiv) {
                errorDiv.textContent = 'Authenticating... please try again in a moment.';
                errorDiv.style.display = 'block';
                setTimeout(function() {
                    errorDiv.style.display = 'none';
                }, 3000);
            }
            return false;
        }

        console.log('[Chatbot] SSO ready, opening panel...');

        // Load iframe only when opening (lazy load)
        if (!iframeLoaded) {
            console.log('[Chatbot] Setting iframe src:', chatbotUrl);

            // Set up timeout to detect if iframe doesn't load
            loadTimeout = setTimeout(function() {
                console.error('[Chatbot] Iframe load timeout - page may be blocking iframe embedding');
                if (errorDiv) {
                    errorDiv.textContent = 'The chatbot page is taking too long to load. It may be blocking iframe embedding. Check console for X-Frame-Options errors.';
                    errorDiv.style.display = 'block';
                }

                // Try to detect if iframe is blocked
                try {
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                    console.log('[Chatbot] Iframe document accessible:', !!iframeDoc);
                } catch (e) {
                    console.error('[Chatbot] Cannot access iframe content (likely CORS/X-Frame-Options blocked):', e);
                }
            }, 10000); // 10 second timeout

            // Set iframe src
            iframe.src = chatbotUrl;
            console.log('[Chatbot] Iframe src set, waiting for load event...');

            // Hide loading indicator when iframe loads
            iframe.onload = function() {
                console.log('[Chatbot] ✓ Iframe onload event fired!');
                clearTimeout(loadTimeout);
                iframeLoaded = true;

                if (loading) {
                    loading.style.display = 'none';
                }

                // Additional check - try to access iframe
                setTimeout(function() {
                    try {
                        const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                        console.log('[Chatbot] Iframe document after load:', iframeDoc);
                        console.log('[Chatbot] Iframe location:', iframe.contentWindow.location.href);
                    } catch (e) {
                        console.log('[Chatbot] Cannot access iframe content (expected for cross-origin):', e.message);
                    }
                }, 100);
            };

            iframe.onerror = function(error) {
                console.error('[Chatbot] ✗ Iframe onerror event fired:', error);
                clearTimeout(loadTimeout);
                if (loading && errorDiv) {
                    errorDiv.textContent = 'Failed to load chatbot. The page may be blocking iframe embedding.';
                    errorDiv.style.display = 'block';
                }
            };

            // Monitor for console errors
            console.log('[Chatbot] Watch your console for any "Refused to display" or "X-Frame-Options" errors');

        } else {
            console.log('[Chatbot] Iframe already loaded previously');
        }

        panel.classList.add('open');
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
        console.log('[Chatbot] Panel opened');

        return false;
    }

    // Close panel
    function closePanel(e) {
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }
        console.log('[Chatbot] Closing panel...');
        panel.classList.remove('open');
        overlay.classList.remove('active');
        document.body.style.overflow = '';
        console.log('[Chatbot] Panel closed');

        return false;
    }

    // Event listeners
    if (bubble) {
        bubble.addEventListener('click', function(e) {
            console.log('[Chatbot] Bubble clicked');
            openPanel(e);
        });
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', function(e) {
            console.log('[Chatbot] Close button clicked');
            closePanel(e);
        });
    }

    if (overlay) {
        overlay.addEventListener('click', function(e) {
            console.log('[Chatbot] Overlay clicked');
            closePanel(e);
        });
    }

    // Close on escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && panel.classList.contains('open')) {
            console.log('[Chatbot] ESC key pressed');
            closePanel(e);
        }
    });

    console.log('[Chatbot] Initialization complete');
    console.log('[Chatbot] Test URL directly in browser:', chatbotUrl);
})();
</script>
"""

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


async def install_button(client_id: str):
    screenshot_dir = Path(__file__).resolve().parent / "screenshots" / client_id
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR = screenshot_dir  # shadows nothing — kept local to this run

    op = OnePasswordManager()
    secrets = await op.get_flattened_client_item(client_id)
    base_url = secrets.get("imis_base_url")
    username = secrets.get("username")
    password = secrets.get("password")
    if not all([base_url, username, password]):
        print(f"Missing credentials for {client_id}: {secrets.keys()}")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print(f"[{client_id}] logging in...")
            await login(page, base_url, username, password, login_url=LOGIN_URL_OVERRIDES.get(client_id))
            await page.screenshot(path=str(SCREENSHOT_DIR / "01_after_login.png"), full_page=True)
            print("  logged in, screenshot saved: 01_after_login.png")

            print("  clicking RiSE...")
            await page.locator(RISE_LINK_SELECTOR).first.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(SCREENSHOT_DIR / "02_after_rise.png"), full_page=True)
            print("  screenshot saved: 02_after_rise.png")

            print("  clicking Page Builder...")
            await page.locator(PAGE_BUILDER_SELECTOR).first.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(SCREENSHOT_DIR / "03_after_page_builder.png"), full_page=True)
            print("  screenshot saved: 03_after_page_builder.png")

            print("  clicking Manage content...")
            await page.locator(MANAGE_CONTENT_SELECTOR).first.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "04_after_manage_content.png"), full_page=True)
            print("  screenshot saved: 04_after_manage_content.png")

            print("  clicking Web folder...")
            try:
                await page.locator(WEB_FOLDER_SELECTOR).first.click(timeout=10000)
            except Exception:
                names = await page.locator("span.rtIn.TreeNode").all_text_contents()
                print(f"  Could not find a top-level 'Web' folder for {client_id}.")
                print(f"  Top-level folders found instead: {names}")
                print("  This client likely uses a different content structure — needs manual mapping.")
                raise
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(SCREENSHOT_DIR / "05_after_web_folder.png"), full_page=True)
            print("  screenshot saved: 05_after_web_folder.png")

            print("  selecting Member Home...")
            await page.locator(MEMBER_HOME_ITEM_SELECTOR).first.click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "06_after_member_home_select.png"), full_page=True)
            print("  screenshot saved: 06_after_member_home_select.png")

            print("  clicking Edit...")
            await page.locator(EDIT_BUTTON_SELECTOR).first.click()
            await page.wait_for_timeout(6000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "07_after_edit.png"), full_page=True)
            print("  screenshot saved: 07_after_edit.png")

            print("  finding frame with Add content link...")
            frame = await find_frame_with_selector(page, ADD_CONTENT_LINK_SELECTOR, timeout=10000)
            target = frame if frame is not None else page
            print(f"  found in: {'iframe' if frame is not None else 'main page'}")

            print("  clicking Add content...")
            await target.locator(ADD_CONTENT_LINK_SELECTOR).first.click()
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "08_after_add_content.png"), full_page=True)
            print("  screenshot saved: 08_after_add_content.png")

            print("  finding frame with Content Html item...")
            frame = await find_frame_with_selector(page, CONTENT_HTML_ITEM_SELECTOR, timeout=10000)
            target = frame if frame is not None else page
            print(f"  found in: {'iframe' if frame is not None else 'main page'}")

            print("  clicking Content Html to select it...")
            await target.locator(CONTENT_HTML_ITEM_SELECTOR).first.click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "08b_after_select_content_html.png"), full_page=True)
            print("  screenshot saved: 08b_after_select_content_html.png")

            print("  finding frame with OK button (Content gallery)...")
            frame = await find_frame_with_selector(page, CONTENT_GALLERY_OK_BUTTON_SELECTOR, timeout=10000)
            target = frame if frame is not None else page
            print(f"  found in: {'iframe' if frame is not None else 'main page'}")

            print("  clicking OK (confirm Content Html)...")
            await target.locator(CONTENT_GALLERY_OK_BUTTON_SELECTOR).first.click()
            await page.wait_for_timeout(4000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "09_after_ok.png"), full_page=True)
            print("  screenshot saved: 09_after_ok.png")

            print("  finding frame with Convert to Advanced Content button...")
            frame = await find_frame_with_selector(page, CONVERT_TO_ADVANCED_SELECTOR, timeout=10000)
            target = frame if frame is not None else page
            print(f"  found in: {'iframe' if frame is not None else 'main page'}")

            print("  clicking Convert to Advanced Content...")
            await target.locator(CONVERT_TO_ADVANCED_SELECTOR).first.click()
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "10_after_convert_advanced.png"), full_page=True)
            print("  screenshot saved: 10_after_convert_advanced.png")

            print("  finding frame with Content Item Name field...")
            frame = await find_frame_with_selector(page, CONTENT_ITEM_NAME_SELECTOR, timeout=10000)
            target = frame if frame is not None else page
            print(f"  found in: {'iframe' if frame is not None else 'main page'}")

            print(f"  filling Content Item Name with '{CONTENT_ITEM_NAME}'...")
            name_field = target.locator(CONTENT_ITEM_NAME_SELECTOR).first
            await name_field.fill("")
            await name_field.fill(CONTENT_ITEM_NAME)
            await page.wait_for_timeout(500)
            await page.screenshot(path=str(SCREENSHOT_DIR / "11_after_name_fill.png"), full_page=True)
            print("  screenshot saved: 11_after_name_fill.png")

            print("  clicking HTML tab...")
            await target.locator(HTML_TAB_SELECTOR).first.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(SCREENSHOT_DIR / "12_after_html_tab.png"), full_page=True)
            print("  screenshot saved: 12_after_html_tab.png")

            print(f"  pasting button HTML (client_id swapped: {_TEMPLATE_CLIENT_ID} -> {client_id})...")
            button_html = BUTTON_HTML_TEMPLATE.replace(_TEMPLATE_CLIENT_ID, client_id)
            frame = await find_frame_with_selector(page, HTML_TEXTAREA_SELECTOR, timeout=10000)
            target = frame if frame is not None else page
            print(f"  found textarea in: {'iframe' if frame is not None else 'main page'}")
            await target.locator(HTML_TEXTAREA_SELECTOR).first.fill(button_html)
            await page.wait_for_timeout(1000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "13_after_html_paste.png"), full_page=True)
            print("  screenshot saved: 13_after_html_paste.png")

            print("  finding frame with item OK button...")
            frame = await find_frame_with_selector(page, ITEM_OK_BUTTON_SELECTOR, timeout=10000)
            target = frame if frame is not None else page
            print(f"  found in: {'iframe' if frame is not None else 'main page'}")

            print("  clicking OK (save content item)...")
            await target.locator(ITEM_OK_BUTTON_SELECTOR).first.click()
            await page.wait_for_timeout(4000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "14_after_item_ok.png"), full_page=True)
            print("  screenshot saved: 14_after_item_ok.png")

            print("  finding frame with Save & Publish button...")
            frame = await find_frame_with_selector(page, SAVE_AND_PUBLISH_SELECTOR, timeout=10000)
            target = frame if frame is not None else page
            print(f"  found in: {'iframe' if frame is not None else 'main page'}")

            print("  clicking Save & Publish...")
            await target.locator(SAVE_AND_PUBLISH_SELECTOR).first.click()
            await page.wait_for_timeout(5000)
            await page.screenshot(path=str(SCREENSHOT_DIR / "15_after_save_publish.png"), full_page=True)
            print("  screenshot saved: 15_after_save_publish.png")

            print("done — PUBLISHED")
        except Exception as e:
            print(f"FAILED: {e}")
            await page.screenshot(path=str(SCREENSHOT_DIR / "FAIL.png"), full_page=True)
        finally:
            await browser.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 insert_button.py <client_id>")
        sys.exit(1)
    asyncio.run(install_button(sys.argv[1]))
