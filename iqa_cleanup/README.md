# iqa_cleanup

Playwright tool that stages deletion of legacy IQAs across iMIS
environments, via the RiSE Intelligent Query Architect UI. There's no REST
API for this — it only exists as a RiSE screen, so this drives the real
browser instead. Same pattern/precedent as `bo_cleanup`.

## Why

`demo42` is the golden environment. 9 IQAs exist in 25/25 non-golden
environments but were removed from `demo42` — legacy/deprecated leftovers
that need to be cleaned up everywhere else to match golden:

- `AiParts/Profile/shared_tags`
- `AiParts/Profile/tags_by_id`
- `Segments/tag_refresh_age`
- `Segments/tag_refresh_change_log`
- `Segments/tag_refresh_name_log`
- `Segments/tag_refresh_paid_through`
- `Segments/tag_refresh_tenure`
- `Segments/tags_added_by_date`
- `Segments/tags_deleted_by_date`

`healthcheck/iqa_healthcheck.py`'s Section 4 ("Extra IQAs") is what surfaces
these — see `reports/extra_iqas_report_20260720.xlsx` for the full breakdown
by item and by environment.

## Safety model

- **Hardcoded allowlist** (`TARGET_ITEMS`, folder + name pairs) — only these
  exact items are ever touched. Nothing is derived dynamically.
- **Dialog message verification** — the delete confirmation is a native
  `window.confirm()` dialog. The script reads its message and only accepts
  if it actually contains the target item's name; otherwise it dismisses
  (Cancel) and skips that item instead of proceeding blind.
- **Stage, never publish** — deleting only moves the IQA to the Recycle Bin
  and sets it to "Working" (draft) status. The live system isn't affected
  until someone explicitly publishes. This script never publishes.
- **Not found = skip, not error** — if a target item doesn't exist in an
  environment (already deleted, or never existed there), it's logged and
  skipped. Safe to re-run.
- **Re-navigates to the target folder before every item**, not just once
  per folder — a successful delete's confirmation/close can reset the tree
  view, so the script never assumes it's still inside the same folder for
  the next item.

## Usage

1. Edit `TARGET_ITEMS` and `ENV_NAMES` at the top of `delete_extra_iqas.py`
   if the scope has changed.
2. Run it:
   ```
   python3 iqa_cleanup/delete_extra_iqas.py
   ```

Runs with a **headed** (visible) Chromium browser per environment, one at a
time. Prints a per-environment, per-item summary
(`deleted` / `not_found` / `mismatch` / `error`) at the end.

## Known limitation

A few environments have a sidebar/menu layout where RiSE lands on the
public homepage instead of the staff console, or where the RiSE flyout is
collapsed behind an expanded module (same issue documented in
`bo_cleanup/README.md`). `LOGIN_URL_OVERRIDES` lets you point a specific
environment at a direct staff URL to work around the first case; the
sidebar-layout case still needs manual handling.

## Known selectors (Telerik/ASP.NET controls in the RiSE staff site)

| Step | Selector |
|---|---|
| RiSE menu | `a.RiSELink` |
| Intelligent Query Architect | `a[href*='/Staff/AsiCommon/Controls/IQA/Default.aspx']` |
| Folder node in tree | `span.rtIn.TreeNode:text-is('<folder name>')` |
| IQA row in filtered list | `span.ObjectBrowserContentListName:has-text('<name>')` (falls back to plain text match) |
| Organize menu | `span.rmText.rmExpandDown:text-is('Organize')` |
| Delete menu item | `span.rmText:text-is('Delete')` |
| "Recycled" confirmation Close button | `#ctl00_CancelButton` |
