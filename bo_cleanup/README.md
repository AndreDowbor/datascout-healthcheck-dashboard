# bo_cleanup

Playwright tool that stages deletion of legacy Business Objects across iMIS
environments, via the RiSE Business Object Designer UI. There's no REST API
for this — it only exists as a RiSE screen, so this drives the real browser
instead.

## Why

`demo42` is the golden environment. A handful of Business Objects exist in
nearly every other environment but were removed from `demo42` — they're
legacy/deprecated and need to be cleaned up everywhere else to match golden.
`healthcheck/bo_healthcheck.py`'s extra-BO detection (`details.extra` in its
Supabase rows, or the `🟣 ... (extra, not in golden)` console lines) is what
surfaces these.

## Safety model

- **Hardcoded allowlist** (`TARGET_BOS`) — only these exact names are ever
  touched. Nothing is derived dynamically at runtime.
- **Dialog message verification** — the delete confirmation is a native
  `window.confirm()` dialog. The script reads its message and only accepts
  if it actually contains the target BO's name; otherwise it dismisses
  (Cancel) and skips that BO instead of proceeding blind.
- **Stage, never publish** — deleting only moves the BO to Recycle Bin and
  sets it to "Working" (draft) status. The live system isn't affected until
  someone explicitly clicks **Publish** on the root business object — this
  script never does that.
- **Not found = skip, not error** — if a target BO doesn't exist in an
  environment (already deleted, or never existed there), it's logged and
  skipped. Safe to re-run.

## Known limitation

Not everything under `$/Common/Business Objects` (Type=BUS) is deletable
this way. **Panels** (e.g. `Datascout_Tags`) show up as Business Objects but
the Organize menu has no Delete option for them at all — confirmed by
testing against demo86. Panels need a different removal path (likely
Panel/Page Designer) that this tool doesn't cover.

## Usage

1. Edit `TARGET_BOS` and `ENV_NAMES` at the top of `delete_extra_bos.py` if
   the scope has changed.
2. Run it:
   ```
   python3 bo_cleanup/delete_extra_bos.py
   ```

Runs with a **headed** (visible) Chromium browser per environment, one at a
time, fully automated (no manual pauses) — the Quick Find filter is driven
programmatically. Prints a per-environment, per-BO summary
(`deleted` / `not_found` / `mismatch` / `error`) at the end.

To test against a single environment before a full run, see the pattern
used during development: import `delete_extra_bos` as a module and call
`await process_env(playwright, "env_name", creds)` directly instead of
running the full `ENV_NAMES` loop.

## Known selectors (Telerik/ASP.NET controls in the RiSE staff site)

| Step | Selector |
|---|---|
| Business Object Designer link | `a[href*='/Staff/AsiCommon/Controls/BOA/Default.aspx']` |
| Quick Find filter input | `#ctl01_TemplateBody_ObjectBrowser1_ObjectQuickFindTextBox` (needs `press_sequentially`, not `.fill()`, to trigger its `onkeyup` filter) |
| BO row in filtered list | `span.ObjectBrowserContentListName:has-text('<name>')` |
| Organize menu | `span.rmText.rmExpandDown:text-is('Organize')` |
| Delete menu item | `span.rmText:text-is('Delete')` |
| "Recycled" confirmation Close button | `#ctl00_CancelButton` |
