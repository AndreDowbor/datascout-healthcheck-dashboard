# iqa_import

Playwright tool to import an IQA package (`.xml` export from the iMIS
Intelligent Query Architect) into a specific folder of an iMIS environment,
via the RiSE staff site UI. There is no REST API for this — it only exists
as a RiSE screen, so this drives the real browser instead.

## When to use this

After running the IQA healthcheck (`healthcheck/iqa_healthcheck.py`) and
finding something broken/missing/out of sync in an environment, use this
script to push a corrected IQA package into that environment's
`$/_DataScout` folder.

## Usage

1. Export the IQA package from the golden record environment (RiSE >
   Intelligent Query Architect > select folder/items > `Export`) — this
   produces the `.xml` package file.
2. Edit the constants at the top of `import_iqa_package.py`:
   - `ENV_NAME` — the client_id as stored in 1Password (e.g. `demo86`)
   - `IQA_FOLDER_NAME` — destination folder name in the IQA tree (e.g. `_DataScout`)
   - `PACKAGE_PATH` — absolute path to the exported `.xml` package on your machine
3. Run it:
   ```
   python3 iqa_import/import_iqa_package.py
   ```

It launches a **headed** (visible) Chromium browser so you can watch it run,
and pauses at the end (Playwright Inspector) so you can review the result
before it closes.

## What it does

1. Fetches `imis_user`/`imis_password`/`imis_base_url` for `ENV_NAME` from
   1Password and logs into the iMIS staff site.
2. Clicks through: **RiSE** → **Intelligent Query Architect** → the
   `IQA_FOLDER_NAME` folder node → **Import**.
3. Selects `PACKAGE_PATH` in the upload form's file input (via
   `set_input_files` — no OS file dialog involved) and clicks **Upload**.
4. On the confirmation screen (list of items in the package, all checked by
   default, "Overwrite existing objects" checked), clicks the final
   **Import** button — this is the step that actually writes to iMIS.
5. Polls the **Messages** box for up to ~120s, screenshotting every 5s to
   `iqa_import/screenshots/progress_XXXs.png` and printing the message text
   whenever it changes, so you can see exactly what succeeded/failed.

## Known selectors (Telerik controls in the RiSE staff site)

| Step | Selector |
|---|---|
| RiSE menu | `a.RiSELink` |
| Intelligent Query Architect | `a[href*='/Staff/AsiCommon/Controls/IQA/Default.aspx']` |
| Folder node in tree | `span.rtIn.TreeNode:text-is('<folder name>')` |
| Import toolbar button | `span.rmText:text-is('Import')` |
| File input (upload form) | `#ctl00_TemplateBody_FileUploadfile0` |
| Upload button | `#ctl00_TemplateBody_UploadButton` |
| Final Import button | `#ctl00_TemplateBody_ImportButton` |

The Import dialog renders inside an iframe, not the top-level page — the
script searches all `page.frames` for the file input rather than assuming
the main frame.

## Known/expected message

If the destination folder (or a subfolder in the package) already exists,
you'll see per-item lines like:

```
Segments: Error: Document already exists in the current path. Create a copy to import.
```

This is benign — it only applies to **folder** objects, which aren't
recreated if they already exist. Actual IQA queries in the package still
import/overwrite normally and show `Information: Successfully imported.`
Only worry if a query (not a folder) shows an error.

## Notes

- Screenshots go to `iqa_import/screenshots/` (gitignored — not committed).
- This has only been run against `demo86` so far. The click path was
  confirmed manually there; other environments may have slightly different
  layouts (custom menus, different folder names) worth spot-checking before
  a wider rollout.
