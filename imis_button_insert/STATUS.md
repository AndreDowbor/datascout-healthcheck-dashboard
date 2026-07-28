# Datascout Concierge bot rollout — status

Last updated: 2026-07-22

## What this is

Rolling out the Datascout Concierge chat bot to staging client_ids that had SSO
expected in `concierge_config` but no bot actually configured. Each client
needs **two independent halves**, both required:

1. **Backend** — an INSERT into `concierge_config` (Supabase, staging). Fields:
   `bot_name`, default `logo_url`/`primary_color`/`suggestions`, `enable_sso_login`,
   and `sso_login_url` built as `{imis_base_url}{sso_path}` from
   `client_config.config_json.credentials.imis` for that client.
2. **Frontend** — the actual chat bubble button installed on the client's iMIS
   "Member Home" page (`@/Web/Member Home` in Page Builder → Manage content),
   via `imis_button_insert/insert_button.py <client_id>` (Playwright).

Rule: always do backend before frontend, for every client — doing only one
causes problems (the button's SSO/webhook flow depends on the backend row
existing).

## Original list (12 client_ids)

`armdemo96`, `atdemo2`, `atdemo81`, `atsdemo89`, `atsdemo90`, `ensyncdemo13`,
`i8vdemo13`, `ibcdemo80`, `isgdemo106`, `isgdemo14`, `dsai` (turned out to
actually be `demo86`), `demosales33`.

## Status

### ✅ Fully done (backend + frontend) — 12 of 12 — rollout complete

| client_id | Notes |
|---|---|
| `armdemo96` | First one built/validated end-to-end. Reference for the whole flow. |
| `atsdemo89` | Standard flow, no issues. |
| `atsdemo90` | Standard flow, no issues. |
| `ibcdemo80` | Standard flow, no issues. |
| `isgdemo106` | Needed a login URL override — landing on `base_url + "/"` hit the public homepage instead of the staff console. Fixed via `/staff` suffix. |
| `isgdemo14` | Same login URL issue as isgdemo106, same fix. |
| `demo86` | This was the real identity of "dsai" from the original list. |
| `atdemo2` | Backend done by the automation. **Frontend done manually by Andrew** (script couldn't find "Web" — see below). |
| `ensyncdemo13` | Backend done by the automation. **Frontend done manually by Andrew** (script couldn't find "Web" — see below). |
| `i8vdemo13` | Backend done by the automation. **Frontend done manually by Andrew** — no "Web" folder here either; instead added an HTML content item directly in the **"Datascout" folder under Shared Content**, not the "I8V" folder that had been guessed as the likely target. Note: this client has a separate, unresolved issue where the Concierge greeting fails with an HTTP 500 from the n8n workflow — see `ISSUE_i8vdemo13_greeting_500.md`. Button install itself is done; the chat isn't fully working yet. |
| `demosales33` | Backend done by the automation. **Frontend done manually by Andrew** — same pattern as i8vdemo13: added a web content item in the **"Datascout" folder under Shared Content**, not via the complex donor/fundraising top-level tree. |
| `atdemo81` | Backend done by the automation. **Frontend done manually by Andrew** — same pattern again: web content item in the **"Datascout" folder under Shared Content**, despite the `ABOTA Demo`/`ASLMS Demo` top-level folders suggesting a more complex structure. |

All 12 client_ids now have both halves done. The "Datascout" folder under
Shared Content ended up being the fallback location for every client
lacking a top-level "Web" folder (3 of 3: i8vdemo13, demosales33, atdemo81) —
worth building into `insert_button.py` as the first fallback path for any
future client onboarding, instead of guessing from the top-level folder name.

(`ensyncdemo13`'s folder list, for reference, before it was done manually: a
large multi-tenant tree — `Arkansas`, `Florida`, `Texas`, `FPA`, `HKE`,
`Keystone`, `LexLedge`, `MBRR`, `NRMCA`, `OKMED`, `PFF`, `PHA`, `VCRealtor`,
`WFCA`, etc.)

## Tooling notes

- `insert_button.py` lives in this folder. Usage: `python3 insert_button.py <client_id>` (needs the `/opt/homebrew/bin/python3.11` interpreter — has `playwright`, `onepassword` SDK, `dotenv` installed; Chromium already downloaded via `ms-playwright` cache).
- `LOGIN_URL_OVERRIDES` dict in the script holds per-client login URL fixes (e.g. `/staff` suffix) for environments where `base_url + "/"` lands on the wrong page.
- When the script can't find a top-level "Web" folder, it now auto-prints the actual top-level folder list instead of just timing out — use that to decide on a fallback mapping.
- Screenshots from every run are saved per-client under `screenshots/<client_id>/`.
- **Add-only rule**: never delete/overwrite an existing `concierge_config` row — always check it's absent first, then INSERT.

## Next steps

- Rollout of the 12 original client_ids is done. If more clients get onboarded later, teach `insert_button.py` to check for a "Datascout" folder under Shared Content as the first fallback when no top-level "Web" folder exists (confirmed working location 3 of 3 times: i8vdemo13, demosales33, atdemo81) — would avoid doing this by hand each time.
- ~~Confirm `i8vdemo13`'s "I8V" folder is really the right target before wiring it in.~~ Resolved — the real target was a "Datascout" folder under Shared Content instead, done manually.
- Investigate `i8vdemo13`'s separate greeting-500 issue (`ISSUE_i8vdemo13_greeting_500.md`) — button is installed but the chat doesn't fully work yet. This is the only remaining open item across the whole rollout.
