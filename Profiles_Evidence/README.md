# Profiles Evidence — Screenshot Archive

Organized 2026-07-24. Every screenshot produced by `New_Profile_Tester/` — the
Datascout Profile embed health check — grouped by what it proves, then by
month. Source: `New_Profile_Tester/screenshots/` and
`New_Profile_Tester/profile_url_screenshots/` (all runs from 2026-03 through
today).

**Not included:** `imis_button_insert/screenshots/` (Concierge chat button
install — a different feature, not the Profile embed) and
`chat-monitor/New_Profile_Tester/screenshots/` (a stale, abandoned duplicate
copy of this same tool, last run 2026-05-01 — flagged separately for cleanup,
not included here since it would just double-count old data).

## Categories

### `01_Bug_Evidence_Direct_Capture/` — 25 files
The single strongest evidence: a direct screenshot of
`https://profiles.staging.app.datascout.ai/{client_id}/profile/126` — the
backend URL the Profile panel actually loads inside an iframe. No iMIS chrome,
just the raw response. When broken, this literally renders:

> 500
> Failed to fetch profile data: Internal Server Error

Captured 2026-07-24 for 25 environments via `screenshot_profile_urls.py`.
One file per environment, named `{client_id}.png`.

### `02_Success/` — 1714 files
`{env}_profile_panel_retest_{timestamp}.png` (or `{env}_profile_panel_{timestamp}.png`
after the 2026-07-24 script simplification) — a screenshot taken after
logging in, clicking the "Datascout Profile" button, reloading, and clicking
again. This is the routine health-check screenshot, taken on every run
regardless of pass/fail status **before** the 2026-07-24 fix — so a file
being in this folder does **not** by itself prove the panel worked, only
that the button was clickable. (The backend-error detection added
2026-07-24 means going forward, a screenshot only lands here if no 5xx was
seen during the flow — see "Known limitation" below for the historical
caveat.)

### `03_Failures_Login/` — 53 files
`{env}_login_debug_{timestamp}.png` plus two one-off
`cpanb_debug_before_submit.png` / `cpanb_debug_after_submit.png` — captured
when the script couldn't find a login form or "Sign In" link at all.

### `04_Failures_Button_Not_Found/` — 78 files
`{env}_datascout_debug_{timestamp}.png` — login succeeded, but the
`#openBtn` (Datascout Profile button) never appeared within 20s. Often
correlates with the session dropping back to the login page mid-flow (see
current investigation notes).

### `05_Failures_CrossDomain_Login/` — 0 files (folder kept for the code path)
Reserved for `{env}_crossdomain_debug_{timestamp}.png` — login failures for
the 4 production-domain environments (`oasw`, `cpanb`, `aboncle`, `aaae`),
which log in via domain redirect instead of the standard iMIS form. No
examples have been captured yet; empty is expected, not a bug in this
archive.

### `06_Adhoc_Manual_Diagnostics/` — 2 files
One-off manual debugging captures, not part of the regular automated run:
`demo42_debug_capture.png` + `demo42_debug_capture.json` (full console/network
log from a manual browser-visible repro of the `demo42` bug on 2026-07-24).

## Known limitation — read before citing "PASS" counts in a meeting

Until 2026-07-24, the health check only verified the button was clickable —
it never checked whether the panel behind it actually loaded real data. The
panel is an iframe to `profiles.staging.app.datascout.ai`; that backend can
500 while the button still clicks fine, which reported as a false PASS with
a screenshot in `02_Success/`. **A screenshot's presence in `02_Success/`
from before 2026-07-24 is not proof the profile actually rendered —
cross-reference against `01_Bug_Evidence_Direct_Capture/` for the same
environment/date if it matters.** This was fixed in
`imis_env_tester_with_1password.py` on 2026-07-24 (now fails on any 5xx
response during the flow, regardless of button state).

### `08_Error_Catalog/` — 9 files
One curated example screenshot per distinct error type found while testing
the direct profile URL (bypassing iMIS staff-page/button flow), 2026-07-24/25
— WHOOPS 500 (3 sub-variants), raw .NET Runtime Error, Datascout-side 500,
Invalid token, stuck SSO spinner, partial success (AI Brief stuck), and a
full-success baseline for comparison. See `08_Error_Catalog/README.md` for
the full breakdown of which environments showed each.

## Current investigation status

**Update 2026-07-27: normalized.** Re-tested all 26 environments both via
the direct URL and via the standard health check script — **25 of 26 now
PASS**, zero 500s of any kind. Only `aaae` still fails, with a distinct,
unrelated error (`502` on `gateway.app.datascout.ai/api/v1/imis-sso/callback`
— a production SSO callback issue, not the staging profiles bug below). The
dominant remaining symptom industry-wide is the "AI Brief" widget getting
stuck on its loading skeleton (see `08_Error_Catalog/README.md`, #8) — a
minor, cosmetic-level issue compared to what was happening before.

**2026-07-24 finding (historical, since resolved):** 17 of 26 tested
staging/demo environments were confirmed hitting a 500 on
`profiles.staging.app.datascout.ai/{env}/profile/{id}` across repeated runs.
See `ISSUE_profiles_staging_500.md` at the repo root for the full technical
writeup of that incident.
