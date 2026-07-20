# iqa_rest_fix

Playwright tool that enables the **"Available via the REST API"** checkbox
on a specific IQA, via the RiSE Intelligent Query Architect UI. There's no
REST API for this setting — it only exists as a checkbox on the query's
Security tab, so this drives the real browser instead.

## Why

The IQA healthcheck (`healthcheck/iqa_healthcheck.py`) reports some IQAs as
**Broken** — `Query: ... not found` (HTTP 400) — even though the query
exists and is otherwise correctly configured. Comparing the golden record
(`demo42`, working) against a broken environment side by side (2026-07-20)
showed everything identical (Access mode, Staff/SysAdmin permissions)
**except** one checkbox: "Available via the REST API" on the query's
Security tab. When unchecked, the query is invisible to `/api/IQA` calls
entirely, regardless of role permissions.

## Safety model

- **Hardcoded target** (`IQA_FOLDER_PATH` / `IQA_ITEM_NAME`) — only that
  exact item is ever touched. Nothing is derived dynamically.
- **Reads before writing** — if the checkbox is already checked, the
  environment is skipped (`already_ok`) and nothing is clicked.
- **Verifies after saving** — after checking the box and clicking Save,
  the item is closed and reopened fresh, and the checkbox is re-read to
  confirm the change actually persisted (not just a client-side postback)
  before it's marked `fixed`.

## Usage

1. Edit `IQA_FOLDER_PATH`, `IQA_ITEM_NAME` and `ENV_NAMES` at the top of
   `fix_rest_availability.py` for the item/environments you're fixing.
2. Run it:
   ```
   python3 iqa_rest_fix/fix_rest_availability.py
   ```

Runs with a **headed** (visible) Chromium browser, one environment at a
time. Prints a per-environment result (`fixed` / `already_ok` / `error` /
`verify_failed`) at the end.

## Known limitation

A few environments land on the public marketing homepage instead of the
staff console when navigating to `base_url + "/"`, or have a sidebar
layout where the RiSE menu is collapsed behind an expanded module (same
issue documented in `bo_cleanup/README.md`). `LOGIN_URL_OVERRIDES` lets
you point a specific environment at a direct staff URL (e.g.
`https://host/Staff`) to work around the first case; the sidebar-layout
case still needs manual handling.

## Known selectors (Telerik controls in the RiSE staff site)

| Step | Selector |
|---|---|
| RiSE menu | `a.RiSELink` |
| Intelligent Query Architect | `a[href*='/Staff/AsiCommon/Controls/IQA/Default.aspx']` |
| Folder node in tree | `span.rtIn.TreeNode:text-is('<folder name>')` |
| Security tab | `a.IQASecurityTab` |
| REST API checkbox | `#ctl00_TemplateBody_DesignShell1_ctl00_LimitRestAvailabilityCheckbox` |

The query editor renders inside a nested iframe (`iMIS/QueryBuilder/Design.aspx`),
not the top-level page or the outer `IQA/Default.aspx` shell frame — the
script searches all `page.frames` for the checkbox rather than assuming
which frame holds it.
