# Error Catalog — Datascout Profile panel

Every distinct failure mode found while testing `profiles.staging.app.datascout.ai/{client}/profile/126`
directly (bypassing the iMIS staff-page/button flow), 2026-07-24 through 2026-07-25.
One representative screenshot per type — same error repeated across multiple
environments, this is just one clean example of each.

Cross-referenced against the re-test on 2026-07-27: **all 8 error types below
had disappeared** — 25 of 26 environments passed cleanly. Kept here as a
reference in case any of these resurface.

---

## 1. iMIS "WHOOPS 500" — Staff login (`Staff_Sign_In.aspx`)
**File:** `01_whoops_staff_signin.png`
The iMIS staff login endpoint itself returns 500 — fails before ever reaching
Datascout. Native iMIS error page, not ours.
**Seen on (2026-07-25):** atdemo81, atsdemo90, demo42, demosales44, ibcdemo80, imisdemo11

## 2. iMIS "WHOOPS 500" — SSO handoff (`DatascoutSSOStaging.aspx`) + stale database
**File:** `02_whoops_sso_staging_database_outdated.png`
Login succeeds, but the page that bridges iMIS → Datascout fails. Two of the
three cases here showed an explicit banner: *"Your database will be out of
date on [date]. Please submit a hosting ticket asking them to run the date
advance script..."* — a concrete, actionable root cause (stale demo database),
distinct from a generic outage.
**Seen on:** demo83, demosales33, demosales50

## 3. iMIS "WHOOPS 500" — Member login (`Sign_In.aspx`, not staff)
**File:** `03_whoops_member_signin.png`
Same WHOOPS page, but on the public/member sign-in path instead of staff —
this client's redirect went to the wrong login flow.
**Seen on:** isgdemo14

## 4. Raw .NET "Runtime Error" (unhandled exception)
**File:** `04_dotnet_runtime_error.png`
Worse than the WHOOPS page — this is what happens when even the *custom
error page* throws while trying to render. The message literally says so:
*"An exception occurred while processing your request. Additionally, another
exception occurred while executing the custom error page for the first
exception."* Double failure.
**Seen on:** demo86, imis36

## 5. Datascout-side 500 — "Failed to fetch profile data"
**File:** `05_datascout_failed_to_fetch.png`
iMIS is fine; the Datascout profiles service itself 500s trying to fetch the
data. This is the error we originally found and reported
(`ISSUE_profiles_staging_500.md`).
**Seen on:** atdemo2, demosales3

## 6. "Invalid token"
**File:** `06_invalid_token.png`
Login succeeds, the real member portal renders (branded site, logged-in
user visible) — but the SSO token handed to Datascout fails validation.
**Seen on:** demosales28, ensyncdemo13, isgdemo106

## 7. Stuck on "Authenticating via IMIS SSO..." — never resolves
**File:** `07_stuck_sso_spinner.png`
The auth handshake spinner just hangs — no error, no success, indefinitely
(captured after a 10s wait with nothing changing).
**Seen on:** imis87

## 8. Partial success — profile loads, "AI Brief" widget stuck loading
**File:** `08_partial_success_ai_brief_stuck.png`
The main profile panel renders with real data, but the AI Brief card never
resolves past its grey skeleton-loader state. This was the *minority* pattern
on 2026-07-25 (2 cases) — by 2026-07-27 it became the *majority* result (16 of
26), after all the harder failures above had cleared up.
**Seen on:** atsdemo89, i8vdemo13 (2026-07-25); most environments (2026-07-27)

## 9. Full success — baseline, for comparison
**File:** `09_full_success_baseline.png`
What it's supposed to look like: profile data **and** a fully-populated AI
Brief with real bullet points.
**Seen on:** armdemo96, bsidemo27 (2026-07-25); most environments by 2026-07-27
