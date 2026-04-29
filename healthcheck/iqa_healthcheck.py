"""
iqa_healthcheck.py — IQA structure healthcheck across all DataScout environments.

Converted from iqa_healthcheck.ipynb. Pushes a summary to Supabase after each run.

Usage:
    python3 iqa_healthcheck.py
"""

import asyncio
import datetime as dt
import math
import os
import sys
import time
import webbrowser
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")

from common.onepassword_manager import OnePasswordManager
from common.imis_client import IMISClient

# ── Config ─────────────────────────────────────────────────────────────────
GOLDEN_RECORD   = "demo83"
IQA_ROOT        = "$/_DataScout"
DEMO_EXCLUDE    = "$/_DataScout/Demo"
IQA_EXCLUDE_PATHS = {"$/_DataScout/TestJamesQuery"}
SAMPLE_LIMIT    = 5
REQUEST_TIMEOUT = 15

# Per-environment timeout overrides (seconds) for envs with large databases
ENV_TIMEOUTS = {
    "aboncle": 30,
}

CLIENT_IDS = [
    "demo83",
    "aaae", "atsdemo89", "aboncle", "armdemo96", "imisdemo11", "imis36",
    "apimisdemo25", "imis87", "imis104", "demosales3", "demosales50", "demosales39",
    "atdemo2", "atdemo81", "demo42", "bsidemo27", "demo86",
    "ensyncdemo13", "i8vdemo13", "ibcdemo80", "isgdemo14", "isgdemo106",
    "oasw", "cpanb",
]

URL_OVERRIDES = {
    "cpanb": "https://staff.cpanewbrunswick.ca/",
    "demosales50": "https://demosales50.imiscloud.com/",
}

STATUS_ICON = {
    "working":      "✅ Working",
    "empty":        "⚠️  Empty",
    "params":       "⚠️  Params",
    "broken":       "❌ Broken",
    "missing":      "❌ Missing",
    "login_failed": "❌ Login Failed",
}


# ── IQA probe ──────────────────────────────────────────────────────────────

def probe_iqa(client: IMISClient, path: str, limit: int = 5, timeout: int = 15, retries: int = 1) -> dict:
    if client.token_expiration is None or dt.datetime.now() >= client.token_expiration:
        client.authenticate()

    url     = f"{client.base_url}/api/IQA"
    params  = {"QueryName": path, "limit": limit, "offset": 0}
    headers = {"Authorization": client.token}

    t0 = time.time()
    last_result = None
    for attempt in range(retries + 1):
        try:
            resp     = requests.get(url, params=params, headers=headers, timeout=timeout)
            duration = round(time.time() - t0, 2)

            if resp.status_code in (200, 400):
                break  # Definitive result — no retry needed

            # Non-200/400: transient server error — retry once
            try:    msg = resp.json().get("Message") or resp.text[:300]
            except: msg = resp.text[:300]
            last_result = {"status": "broken", "http_status": resp.status_code, "total_count": 0,
                           "sample_rows": [], "error_msg": msg, "duration_sec": duration}
            if attempt < retries:
                time.sleep(3)
                if client.token_expiration is None or dt.datetime.now() >= client.token_expiration:
                    client.authenticate()
                headers = {"Authorization": client.token}
                continue

            return last_result

        except requests.exceptions.Timeout:
            last_result = {"status": "broken", "http_status": None, "total_count": 0,
                           "sample_rows": [], "error_msg": f"Timeout after {timeout}s",
                           "duration_sec": round(time.time() - t0, 2)}
            if attempt < retries:
                time.sleep(3)
                continue
            return last_result
        except Exception as e:
            return {"status": "broken", "http_status": None, "total_count": 0,
                    "sample_rows": [], "error_msg": str(e),
                    "duration_sec": round(time.time() - t0, 2)}

    # resp is now a definitive 200 or 400
    duration = round(time.time() - t0, 2)
    if resp.status_code == 200:
        data  = resp.json()
        total = data.get("TotalCount", 0)
        sample = []
        for row in data.get("Items", {}).get("$values", [])[:limit]:
            rec = {}
            for kv in row.get("Properties", {}).get("$values", []):
                v = kv.get("Value")
                rec[kv["Name"]] = v.get("$value", v) if isinstance(v, dict) else v
            sample.append(rec)
        return {
            "status": "working" if total > 0 else "empty",
            "http_status": 200, "total_count": total,
            "sample_rows": sample, "error_msg": None, "duration_sec": duration,
        }
    else:  # 400 — could be "params required" or a SQL/server error
        try:    msg = resp.json().get("Message") or resp.text[:300]
        except: msg = resp.text[:300]
        # SQL errors (overflow, conversion, etc.) are real failures, not missing params
        SQL_ERROR_SIGNALS = ("overflow", "arithmetic", "conversion failed", "invalid column", "divide by zero")
        if any(s in msg.lower() for s in SQL_ERROR_SIGNALS):
            return {"status": "broken", "http_status": 400, "total_count": 0,
                    "sample_rows": [], "error_msg": msg, "duration_sec": duration}
        return {"status": "params", "http_status": 400, "total_count": 0,
                "sample_rows": [], "error_msg": msg, "duration_sec": duration}


# ── HTML report builder ────────────────────────────────────────────────────

def build_html(now_str, df_data, n_envs, n_iqas, golden_record,
               login_failed_envs, not_deployed_envs, broken_data,
               unexpected_params_data, missing_data, environment_credentials):
    RED    = "#f85149"
    YELLOW = "#e3b341"

    def _http(val):
        return "—" if val is None or (isinstance(val, float) and math.isnan(val)) else int(val)

    def card(content):
        return f'<div class="iqa-block">{content}</div>'

    def section(icon, title, color, body):
        return f"""
        <div class="section">
          <div class="section-header" style="border-left:3px solid {color}">
            <span class="section-title">{icon}&nbsp; {title}</span>
          </div>
          <div class="section-body">{body}</div>
        </div>"""

    def table(headers, rows_html):
        ths = "".join(f"<th>{h}</th>" for h in headers)
        return f"<table><thead><tr>{ths}</tr></thead><tbody>{rows_html}</tbody></table>"

    def ok(msg):
        return f'<p class="ok">✅&nbsp; {msg}</p>'

    # Section 1
    s1 = ""
    if not login_failed_envs and not not_deployed_envs:
        s1 = ok("All environments reachable and DataScout deployed.")
    else:
        if login_failed_envs:
            rows = "".join(
                f"<tr><td class='env'>{e['env']}</td>"
                f"<td class='mono dim'>{environment_credentials.get(e['env'],{}).get('imis_base_url','')}</td>"
                f"<td class='mono red'>{e['error_msg']}</td></tr>"
                for e in login_failed_envs
            )
            s1 += f"""<div class="sub"><div class="sub-title">❌ Login Failed
                <span class="badge">{len(login_failed_envs)}</span></div>
                {table(["Env", "URL", "Error"], rows)}</div>"""
        if not_deployed_envs:
            rows = "".join(
                f"<tr><td class='env'>{env}</td>"
                f"<td class='mono dim'>{environment_credentials.get(env,{}).get('imis_base_url','')}</td></tr>"
                for env in not_deployed_envs
            )
            s1 += f"""<div class="sub"><div class="sub-title">❌ DataScout Not Deployed
                <span class="badge">{len(not_deployed_envs)}</span></div>
                {table(["Env", "URL"], rows)}</div>"""

    # Section 2
    if not broken_data:
        s2 = ok("No broken IQAs.")
    else:
        s2 = ""
        for iqa, group in broken_data.items():
            rows = "".join(
                f"<tr><td class='env'>{r['env']}</td>"
                f"<td class='mono dim'>HTTP {_http(r['http_status'])}</td>"
                f"<td class='mono red'>{r['error_msg']}</td></tr>"
                for r in group
            )
            n = len(group)
            s2 += card(
                f"<div class='iqa-name red'>❌ {iqa} <span class='badge'>{n} env{'s' if n>1 else ''}</span></div>"
                + table(["Env", "HTTP", "Error"], rows)
            )

    # Section 3
    s3 = '<div class="sub-title" style="margin-bottom:12px">⚠️ Unexpected Params <span class="sub-label">— IQA works elsewhere but requires params here</span></div>'
    if not unexpected_params_data:
        s3 += ok("None.")
    else:
        for iqa, group in unexpected_params_data.items():
            envs = ", ".join(sorted(r["env"] for r in group))
            s3 += card(f"<div class='iqa-name yellow'>⚠️ {iqa}</div><div class='affected'>Affected: {envs}</div>")

    s3 += '<div class="sub-title" style="margin-top:24px;margin-bottom:12px">❌ Missing IQAs <span class="sub-label">— deployed elsewhere, absent here</span></div>'
    if not missing_data:
        s3 += ok("None.")
    else:
        for iqa, group in missing_data.items():
            envs = ", ".join(sorted(r["env"] for r in group))
            n = len(group)
            s3 += card(
                f"<div class='iqa-name red'>❌ {iqa} <span class='badge'>{n} env{'s' if n>1 else ''}</span></div>"
                f"<div class='affected'>Affected: {envs}</div>"
            )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DataScout IQA Healthcheck — {now_str}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;line-height:1.6;padding:40px 32px;max-width:1000px;margin:0 auto}}
  header{{margin-bottom:40px;padding-bottom:20px;border-bottom:1px solid #21262d}}
  header h1{{font-size:20px;font-weight:700;margin-bottom:6px;letter-spacing:-0.3px}}
  .meta{{color:#8b949e;font-size:13px}}
  .section{{margin-bottom:28px;border:1px solid #21262d;border-radius:10px;overflow:hidden;background:#161b22}}
  .section-header{{padding:14px 20px;background:#161b22;border-bottom:1px solid #21262d}}
  .section-title{{font-size:14px;font-weight:600;letter-spacing:0.2px}}
  .section-body{{padding:20px}}
  .sub{{margin-bottom:22px}}
  .sub:last-child{{margin-bottom:0}}
  .sub-title{{font-size:13px;font-weight:600;color:#c9d1d9;margin-bottom:10px}}
  .sub-label{{font-weight:400;font-size:12px;color:#6e7681}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}}
  th{{text-align:left;padding:7px 12px;color:#8b949e;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #21262d}}
  td{{padding:9px 12px;border-bottom:1px solid #21262d;vertical-align:top}}
  tr:last-child td{{border-bottom:none}}
  td.env{{font-weight:600;color:#58a6ff;white-space:nowrap}}
  td.mono{{font-family:"SF Mono",Menlo,monospace;font-size:12px}}
  td.dim{{color:#8b949e}}
  td.red{{color:#f85149}}
  .iqa-block{{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:14px 16px;margin-bottom:10px}}
  .iqa-block:last-child{{margin-bottom:0}}
  .iqa-name{{font-size:13px;font-weight:600;margin-bottom:6px}}
  .iqa-name.red{{color:#f85149}}
  .iqa-name.yellow{{color:#e3b341}}
  .affected{{font-size:12px;color:#8b949e;font-family:"SF Mono",Menlo,monospace;margin-top:4px}}
  .badge{{display:inline-block;background:#21262d;color:#8b949e;border-radius:10px;padding:1px 8px;font-size:11px;font-weight:500;margin-left:6px;vertical-align:middle}}
  .ok{{color:#3fb950;font-size:13px;padding:4px 0}}
</style>
</head>
<body>
<header>
  <h1>🔍 DataScout IQA Healthcheck</h1>
  <div class="meta">Generated {now_str} &nbsp;·&nbsp; {n_envs} environments &nbsp;·&nbsp; {n_iqas} IQAs &nbsp;·&nbsp; Golden record: {golden_record}</div>
</header>
{section("🔴", "Section 1 — Environments Down", "#f85149", s1)}
{section("🔴", "Section 2 — Broken IQAs", "#f85149", s2)}
{section("🟡", "Section 3 — IQA Issues", "#e3b341", s3)}
</body>
</html>"""


# ── Supabase push ──────────────────────────────────────────────────────────

def push_to_supabase(all_results, login_failed_envs, not_deployed_envs,
                     broken_data, unexpected_params_data, missing_data, checked_at,
                     expected_params_paths=None):
    sb_url = os.getenv("DASHBOARD_SUPABASE_URL", "")
    sb_key = os.getenv("DASHBOARD_SUPABASE_KEY", "")
    if not sb_url or not sb_key:
        print("  [warn] DASHBOARD_SUPABASE_URL/KEY not set — skipping Supabase push.")
        return

    from supabase import create_client
    supabase = create_client(sb_url, sb_key)

    # Build per-environment summary rows
    envs_seen = {r["env"] for r in all_results}
    rows = []
    for env in envs_seen:
        env_results = [r for r in all_results if r["env"] == env]

        if any(r["env"] == env for r in login_failed_envs):
            status = "DOWN"
        elif env in not_deployed_envs:
            status = "DOWN"
        else:
            expected = expected_params_paths or set()
            has_broken          = any(r["status"] == "broken" for r in env_results)
            has_missing         = any(r["status"] == "missing" for r in env_results)
            has_unexpected_params = any(
                r["status"] == "params" and r["path"] not in expected
                for r in env_results
            )
            if has_broken or has_missing or has_unexpected_params:
                status = "ISSUES"
            else:
                status = "OK"

        expected = expected_params_paths or set()
        issues_count = sum(
            1 for r in env_results
            if r["status"] in ("broken", "missing")
            or (r["status"] == "params" and r["path"] not in expected)
        )

        rows.append({
            "environment": env,
            "status": status,
            "issues_count": issues_count,
            "details": {
                "broken":  [r["path"] for r in env_results if r["status"] == "broken"],
                "missing": [r["path"] for r in env_results if r["status"] == "missing"],
                "params":  [r["path"] for r in env_results if r["status"] == "params"],
            },
            "checked_at": checked_at,
        })

    try:
        supabase.table("iqa_checks").insert(rows).execute()
        print(f"  → Pushed {len(rows)} IQA environment summaries to Supabase.")
    except Exception as exc:
        print(f"  [warn] Supabase push failed: {exc}")


# ── Main ───────────────────────────────────────────────────────────────────

async def main():
    global_start = time.time()
    op = OnePasswordManager()

    # Fetch credentials
    print("Fetching credentials from 1Password...\n")
    environment_credentials = {}
    for client_id in CLIENT_IDS:
        try:
            secrets  = await op.get_flattened_client_item(client_id)
            base_url = secrets.get("imis_base_url")
            username = secrets.get("username")
            password = secrets.get("password")
            if not all([base_url, username, password]):
                print(f"  SKIP  {client_id}: missing field(s).")
                continue
            environment_credentials[client_id] = {
                "imis_base_url": base_url,
                "username": username,
                "password": password,
            }
            print(f"  OK    {client_id}")
        except Exception as e:
            print(f"  FAIL  {client_id}: {e}")

    for env, url in URL_OVERRIDES.items():
        if env in environment_credentials:
            environment_credentials[env]["imis_base_url"] = url

    print(f"\nLoaded {len(environment_credentials)}/{len(CLIENT_IDS)} environments.")

    # Discover IQAs from golden record
    print(f"\nConnecting to golden record: {GOLDEN_RECORD}...")
    g = environment_credentials[GOLDEN_RECORD]
    golden_client = IMISClient(g["imis_base_url"], g["username"], g["password"])
    all_docs = golden_client.list_iqas_in_folder(IQA_ROOT)
    golden_iqas = [
        doc for doc in all_docs
        if doc.get("Type") == "IQD"
        and not (doc.get("Path") or "").startswith(DEMO_EXCLUDE)
        and (doc.get("Path") or "") not in IQA_EXCLUDE_PATHS
    ]
    golden_paths = [doc["Path"] for doc in golden_iqas]
    print(f"✅ {len(golden_paths)} IQAs in golden record.")

    # Run checks
    all_results = []
    for client_id, creds in environment_credentials.items():
        print(f"\n── {client_id} ──")
        try:
            imis = IMISClient(creds["imis_base_url"], creds["username"], creds["password"])
        except Exception as e:
            print(f"  ❌ Login failed: {e}")
            for path in golden_paths:
                all_results.append({"env": client_id, "path": path, "status": "login_failed",
                                     "http_status": None, "total_count": None, "sample_rows": [],
                                     "error_msg": str(e), "duration_sec": 0})
            continue

        try:
            env_docs  = imis.list_iqas_in_folder(IQA_ROOT)
            env_paths = {
                doc["Path"] for doc in env_docs
                if doc.get("Type") == "IQD"
                and not (doc.get("Path") or "").startswith(DEMO_EXCLUDE)
            }
        except Exception as e:
            print(f"  ⚠️  IQA discovery failed: {e}")
            env_paths = set()

        for path in golden_paths:
            if path not in env_paths:
                result = {"status": "missing", "http_status": None, "total_count": 0,
                          "sample_rows": [], "error_msg": "Not in document tree", "duration_sec": 0}
            else:
                timeout = ENV_TIMEOUTS.get(client_id, REQUEST_TIMEOUT)
                result = probe_iqa(imis, path, limit=SAMPLE_LIMIT, timeout=timeout)
            print(f"  {STATUS_ICON[result['status']]:<18} {path}")
            all_results.append({"env": client_id, "path": path, **result})

    global_duration = round(time.time() - global_start, 2)
    print(f"\n\n⏱️  Completed in {global_duration}s across {len(environment_credentials)} environments.")

    # Build analysis sets
    login_failed_envs = []
    seen_login_failed = set()
    for r in all_results:
        if r["status"] == "login_failed" and r["env"] not in seen_login_failed:
            login_failed_envs.append({"env": r["env"], "error_msg": r["error_msg"]})
            seen_login_failed.add(r["env"])

    login_failed_set = {e["env"] for e in login_failed_envs}
    not_deployed_envs = [
        env for env in environment_credentials
        if env not in login_failed_set
        and all(r["status"] == "missing" for r in all_results if r["env"] == env)
    ]
    ignore_envs = login_failed_set | set(not_deployed_envs)

    golden_statuses = {r["path"]: r["status"] for r in all_results if r["env"] == GOLDEN_RECORD}
    expected_params_paths = {p for p, s in golden_statuses.items() if s == "params"}

    broken_data = {}
    for r in all_results:
        if r["status"] == "broken" and r["env"] not in ignore_envs:
            iqa = r["path"].replace("$/_DataScout/", "")
            broken_data.setdefault(iqa, []).append(r)

    unexpected_params_data = {}
    for r in all_results:
        if r["status"] == "params" and r["path"] not in expected_params_paths and r["env"] not in ignore_envs:
            iqa = r["path"].replace("$/_DataScout/", "")
            unexpected_params_data.setdefault(iqa, []).append(r)

    missing_data = {}
    for r in all_results:
        if r["status"] == "missing" and r["env"] not in ignore_envs:
            iqa = r["path"].replace("$/_DataScout/", "")
            missing_data.setdefault(iqa, []).append(r)

    # Save HTML report
    now      = dt.datetime.now()
    now_str  = now.strftime("%Y-%m-%d %H:%M")
    filename = now.strftime("healthcheck_%Y%m%d_%H%M%S.html")
    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_path = reports_dir / filename

    n_envs = len({r["env"] for r in all_results})
    n_iqas = len({r["path"] for r in all_results})

    html = build_html(now_str, all_results, n_envs, n_iqas, GOLDEN_RECORD,
                      login_failed_envs, not_deployed_envs, broken_data,
                      unexpected_params_data, missing_data, environment_credentials)
    report_path.write_text(html, encoding="utf-8")
    print(f"✅ Report saved → {report_path}")
    webbrowser.open(report_path.as_uri())

    # Push to Supabase
    checked_at = dt.datetime.now(dt.timezone.utc).isoformat()
    push_to_supabase(all_results, login_failed_envs, not_deployed_envs,
                     broken_data, unexpected_params_data, missing_data, checked_at,
                     expected_params_paths=expected_params_paths)


if __name__ == "__main__":
    asyncio.run(main())
