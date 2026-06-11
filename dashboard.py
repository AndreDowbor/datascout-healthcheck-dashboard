"""
DataScout Ops Dashboard
Run: python3 -m streamlit run dashboard.py
"""

import base64
import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from supabase import create_client


def _logo_b64() -> str:
    path = Path(__file__).parent / "datascout_logo.png"
    return base64.b64encode(path.read_bytes()).decode() if path.exists() else ""

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="DataScout Ops — Bursting Silver",
    page_icon="🦊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; background-color: #FFF8F4; color: #0D1B3E; }
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding: 2rem 2rem 4rem; max-width: 1400px; }
  .section-label { font-size:15px; font-weight:700; letter-spacing:0.04em; color:#0D1B3E; margin-bottom:0.75rem; margin-top:2rem; }
  .pill-row { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:1.5rem; }
  .pill { padding:4px 14px; border-radius:999px; font-size:12px; font-weight:600; }
  .pill-green  { background:#DCFCE7; color:#15803D; }
  .pill-amber  { background:#FEF3C7; color:#B45309; }
  .pill-red    { background:#FEE2E2; color:#DC2626; }
  .pill-gray   { background:#E2E8F0; color:#64748B; }
  .bot-card { background:#F8F9FA; border:1px solid #F0D8C8; border-radius:10px; padding:14px 16px; margin-bottom:10px; transition:border-color 0.2s, box-shadow 0.2s; }
  .bot-card.up       { border-left:3px solid #FC6305; }
  .bot-card.degraded { border-left:3px solid #D97706; }
  .bot-card.down     { border-left:3px solid #DC2626; }
  a.bot-link { text-decoration:none; display:block; color:#0D1B3E !important; }
  a.bot-link:hover .bot-card { border-color:#FC6305; box-shadow:0 2px 12px rgba(252,99,5,0.14); cursor:pointer; }
  .bot-name { font-size:13px; font-weight:600; color:#0D1B3E; margin-bottom:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .bot-badge { display:inline-block; font-size:10px; font-weight:700; padding:2px 8px; border-radius:999px; letter-spacing:0.05em; margin-bottom:8px; }
  .badge-up       { background:#FFF0E6; color:#FC6305; }
  .badge-degraded { background:#FEF3C7; color:#B45309; }
  .badge-down     { background:#FEE2E2; color:#DC2626; }
  .bot-meta { font-size:11px; color:#7A90AA; display:flex; gap:10px; }
  .last-checked { font-size:11px; color:#8A9FBA; margin-top:5px; }
  .ds-divider { border:none; border-top:1px solid #F0D8C8; margin:2rem 0 0; }
</style>
""", unsafe_allow_html=True)

# ── Table CSS (used inside components.html) ──────────────────────────────────

TABLE_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: transparent; font-family: 'Inter', sans-serif; }
  .table-wrap { background:#FFFFFF; border:1px solid #F0D8C8; border-radius:10px; overflow:hidden; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; padding:9px 14px; color:#FC6305; font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:0.05em; border-bottom:1px solid #F0D8C8; background:#FFF8F4; }
  td { padding:10px 14px; border-bottom:1px solid #FDF0E8; color:#0D1B3E; vertical-align:middle; }
  tr:last-child td { border-bottom:none; }
  tr:hover td { background:#FFF3EC; }
  .env  { font-weight:600; color:#0D1B3E; font-family:monospace; font-size:12px; }
  .ts   { color:#8A9FBA; font-size:11px; }
  .err  { color:#DC2626; font-size:11px; max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .cnt  { color:#5A7A9A; font-size:12px; }
  .s-ok      { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#FFF0E6; color:#FC6305; }
  .s-issues  { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#FEF3C7; color:#B45309; }
  .s-down    { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#FEE2E2; color:#DC2626; }
  .s-pass    { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#FFF0E6; color:#FC6305; }
  .s-fail    { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#FEE2E2; color:#DC2626; }
  .s-warn    { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#FEF3C7; color:#B45309; }
  .s-skip    { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#E2E8F0; color:#64748B; }
</style>
"""

# ── Supabase ─────────────────────────────────────────────────────────────────

def _get_credentials():
    url = st.secrets.get("DASHBOARD_SUPABASE_URL") or os.getenv("DASHBOARD_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
    key = st.secrets.get("DASHBOARD_SUPABASE_KEY") or os.getenv("DASHBOARD_SUPABASE_KEY") or os.getenv("SUPABASE_KEY", "")
    return url, key

@st.cache_resource
def get_supabase():
    url, key = _get_credentials()
    return create_client(url, key)


@st.cache_data(ttl=120)
def fetch_latest(table: str, group_col: str, limit: int = 500) -> list[dict]:
    sb = get_supabase()
    res = sb.table(table).select("*").order("checked_at", desc=True).limit(limit).execute()
    seen = {}
    for row in res.data:
        key = row.get(group_col)
        if key not in seen:
            seen[key] = row
    return list(seen.values())


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_ts(iso):
    if not iso:
        return "—"
    try:
        from datetime import timezone, timedelta
        brt = timezone(timedelta(hours=-3))
        dt = datetime.fromisoformat(iso).astimezone(brt)
        return dt.strftime("%b %d %H:%M BRT")
    except Exception:
        return iso

def fmt_ms(ms):
    if ms is None:
        return "—"
    return f"{ms/1000:.1f}s" if ms >= 1000 else f"{ms}ms"

def status_class(s):
    s = (s or "").upper()
    if s == "UP": return "up"
    if "DEGRADED" in s: return "degraded"
    return "down"

def badge_class(s):
    s = (s or "").upper()
    if s == "UP": return "badge-up"
    if "DEGRADED" in s: return "badge-degraded"
    return "badge-down"

def table_badge(s):
    s = (s or "").upper()
    css = {
        "OK":"s-ok","ISSUES":"s-issues","DOWN":"s-down",
        "PASS":"s-pass","FAIL":"s-fail",
        "AUTH_ERROR":"s-warn","NO_KEY":"s-warn","ERROR":"s-down",
        "SKIP":"s-skip",
    }.get(s,"s-down")
    return f'<span class="{css}">{s}</span>'

def count_statuses(rows, field, values):
    vals = [v.upper() for v in values]
    return sum(1 for r in rows if (r.get(field) or "").upper() in vals)

def escape(s):
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


# ── Header ────────────────────────────────────────────────────────────────────

_logo = _logo_b64()
_logo_html = (
    f'<img src="data:image/png;base64,{_logo}" width="88" height="88" style="border-radius:18px;flex-shrink:0;">'
    if _logo else
    '<span style="font-size:56px;">🦊</span>'
)

col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.markdown(f"""
        <div style="display:flex;align-items:center;gap:18px;margin-bottom:4px;">
          {_logo_html}
          <div>
            <h1 style="font-size:22px;font-weight:800;color:#0D1B3E;margin:0;letter-spacing:-0.5px;">DataScout Ops Dashboard</h1>
            <p style="font-size:13px;color:#7A90AA;margin:6px 0 0;">Platform health across all environments</p>
          </div>
        </div>
    """, unsafe_allow_html=True)
with col_refresh:
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    if st.button("↻  Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("<hr class='ds-divider'>", unsafe_allow_html=True)

# ── Credential guard ──────────────────────────────────────────────────────────

_url, _key = _get_credentials()
if not _url or not _key:
    st.error("Supabase credentials missing. Add DASHBOARD_SUPABASE_URL and DASHBOARD_SUPABASE_KEY to Streamlit secrets.")
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────

with st.spinner("Loading..."):
    concierge_rows = fetch_latest("concierge_checks", "name")
    iqa_rows       = fetch_latest("iqa_checks", "environment")
    profile_rows   = fetch_latest("profile_checks", "environment")
    engage_rows    = fetch_latest("engage_checks", "org")
    algolia_rows   = fetch_latest("algolia_checks", "environment")
    bo_rows        = fetch_latest("bo_checks", "environment")

# ── Summary cards ─────────────────────────────────────────────────────────────

c_up       = count_statuses(concierge_rows, "status", ["UP"])
c_degraded = count_statuses(concierge_rows, "status", ["DEGRADED"])
c_down     = count_statuses(concierge_rows, "status", ["DOWN"])
i_ok       = count_statuses(iqa_rows, "status", ["OK"])
i_issues   = count_statuses(iqa_rows, "status", ["ISSUES"])
i_down     = count_statuses(iqa_rows, "status", ["DOWN"])
p_pass     = count_statuses(profile_rows, "status", ["PASS"])
p_fail     = count_statuses(profile_rows, "status", ["FAIL"])
e_ok       = count_statuses(engage_rows, "status", ["OK"])
e_slow     = count_statuses(engage_rows, "status", ["SLOW"])
e_down     = count_statuses(engage_rows, "status", ["DOWN"])
a_ok       = count_statuses(algolia_rows, "status", ["OK"])
a_warn     = count_statuses(algolia_rows, "status", ["AUTH_ERROR", "NO_KEY"])
a_down     = count_statuses(algolia_rows, "status", ["DOWN", "ERROR"])
b_ok       = count_statuses(bo_rows, "status", ["OK"])
b_issues   = count_statuses(bo_rows, "status", ["ISSUES"])
b_down     = count_statuses(bo_rows, "status", ["DOWN"])

def latest_ts(rows):
    ts = max((r.get("checked_at") or "" for r in rows), default="")
    return fmt_ts(ts) if ts else "—"

def summary_card(title, icon, main_val, main_label, main_color, sub_items, last_checked):
    subs = "".join([
        f'<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #FDF0E8;">'
        f'<span style="font-size:13px;color:#7A90AA;font-weight:500;">{label}</span>'
        f'<span style="font-size:15px;font-weight:700;color:{color};">{val}</span>'
        f'</div>'
        for val, label, color in sub_items
    ])
    return f"""
    <div style="background:#FFFFFF;border:1px solid #F0D8C8;border-top:3px solid #FC6305;border-radius:14px;padding:24px 28px;height:100%;box-shadow:0 1px 6px rgba(252,99,5,0.06);">
      <div style="margin-bottom:20px;">
        <span style="font-size:14px;font-weight:700;letter-spacing:0.03em;color:#FC6305;">{title}</span>
      </div>
      <div style="font-size:52px;font-weight:800;color:#0D1B3E;line-height:1;letter-spacing:-2px;">{main_val}</div>
      <div style="font-size:13px;color:#7A90AA;margin-top:6px;font-weight:400;">{main_label}</div>
      <div style="border-top:1px solid #FDF0E8;margin-top:20px;">{subs}</div>
      <div style="margin-top:16px;display:flex;align-items:center;gap:6px;">
        <span style="width:6px;height:6px;border-radius:50%;background:#FC6305;display:inline-block;flex-shrink:0;"></span>
        <span style="font-size:12px;color:#8A9FBA;">Last checked <strong style="color:#FC6305;">{last_checked}</strong></span>
      </div>
    </div>"""

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    c_total = c_up + c_degraded + c_down
    st.markdown(summary_card(
        "Concierge Bots", "🤖",
        c_up, f"of {c_total} bots online", "#16A34A",
        [(c_degraded, "Degraded", "#D97706"), (c_down, "Down", "#DC2626")],
        latest_ts(concierge_rows)
    ), unsafe_allow_html=True)
with c2:
    i_total = i_ok + i_issues + i_down
    st.markdown(summary_card(
        "IQA Structure", "🔍",
        i_ok, f"of {i_total} environments OK", "#16A34A",
        [(i_issues, "With issues", "#D97706"), (i_down, "Down", "#DC2626")],
        latest_ts(iqa_rows)
    ), unsafe_allow_html=True)
with c3:
    b_total = b_ok + b_issues + b_down
    st.markdown(summary_card(
        "Business Objects", "🗄️",
        b_ok, f"of {b_total} environments OK", "#16A34A",
        [(b_issues, "With issues", "#D97706"), (b_down, "Down", "#DC2626")],
        latest_ts(bo_rows)
    ), unsafe_allow_html=True)
with c4:
    p_total = p_pass + p_fail
    st.markdown(summary_card(
        "Profile Checks", "👤",
        p_pass, f"of {p_total} environments passing", "#16A34A",
        [(0, "Degraded", "#D97706"), (p_fail, "Failing", "#DC2626")],
        latest_ts(profile_rows)
    ), unsafe_allow_html=True)
with c5:
    e_total = e_ok + e_slow + e_down
    st.markdown(summary_card(
        "Engage", "⚡",
        e_ok, f"of {e_total} orgs OK", "#16A34A",
        [(e_slow, "Slow", "#D97706"), (e_down, "Down", "#DC2626")],
        latest_ts(engage_rows)
    ), unsafe_allow_html=True)
with c6:
    a_total = a_ok + a_warn + a_down
    st.markdown(summary_card(
        "Algolia", "🔎",
        a_ok, f"of {a_total} apps OK", "#16A34A",
        [(a_warn, "Auth / No key", "#D97706"), (a_down, "Down", "#DC2626")],
        latest_ts(algolia_rows)
    ), unsafe_allow_html=True)

st.markdown("<div style='margin-top:2rem'></div>", unsafe_allow_html=True)

# ── Section 1: Concierge bot cards ────────────────────────────────────────────

st.markdown('<div class="section-label">Concierge Bots</div>', unsafe_allow_html=True)

if not concierge_rows:
    st.info("No concierge data yet.")
else:
    order = {"DOWN": 0, "DEGRADED": 1, "UP": 2}
    sorted_bots = sorted(
        concierge_rows,
        key=lambda r: (order.get((r.get("status") or "DOWN").upper().split()[0], 3), r.get("name", ""))
    )
    cols = st.columns(5)
    for i, bot in enumerate(sorted_bots):
        name   = bot.get("name", "—")
        status = bot.get("status", "DOWN")
        sc     = status_class(status)
        bc     = badge_class(status)
        http   = fmt_ms(bot.get("http_response_ms"))
        chat   = fmt_ms(bot.get("chat_response_ms"))
        ts     = fmt_ts(bot.get("checked_at"))
        error  = escape(bot.get("error") or "")
        url    = escape(bot.get("url") or "")
        with cols[i % 5]:
            error_html = "" if not error or sc == "up" else f'<div style="font-size:10px;color:#EF4444;margin-top:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{error[:50]}</div>'
            card_inner = (
                f'<div class="bot-name" title="{escape(name)}">{escape(name)}</div>'
                f'<div><span class="bot-badge {bc}">{escape(status)}</span></div>'
                f'<div class="bot-meta"><span>HTTP {http}</span><span>Chat {chat}</span></div>'
                f'{error_html}'
                f'<div class="last-checked">{ts}</div>'
            )
            if url:
                st.markdown(f'<a class="bot-link" href="{url}" target="_blank" rel="noopener noreferrer"><div class="bot-card {sc}">{card_inner}</div></a>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bot-card {sc}">{card_inner}</div>', unsafe_allow_html=True)

# ── Section 2: IQA table ──────────────────────────────────────────────────────

st.markdown("<hr class='ds-divider'><div class='section-label'>IQA Structure</div>", unsafe_allow_html=True)

if not iqa_rows:
    st.info("No IQA data yet.")
else:
    sorted_iqa = sorted(
        iqa_rows,
        key=lambda r: ({"OK":2,"ISSUES":1,"DOWN":0}.get((r.get("status") or "DOWN").upper(), 0), r.get("environment","")),
        reverse=True
    )

    IQA_EXPAND_CSS = """
    <style>
      .iqa-row { cursor: pointer; }
      .iqa-row:hover td { background: #FFF3EC !important; }
      .iqa-row td:first-child .chevron { display:inline-block; margin-right:6px; color:#94A3B8; font-size:10px; transition:transform 0.2s; }
      .iqa-row.open td:first-child .chevron { transform: rotate(90deg); color:#FC6305; }
      .detail-row { display:none; }
      .detail-row.open { display:table-row; }
      .detail-cell { padding:0 14px 12px 32px !important; border-bottom:1px solid #FDF0E8; background:#FFF8F4 !important; }
      .detail-inner { display:flex; gap:24px; flex-wrap:wrap; padding-top:8px; }
      .detail-group { min-width:180px; }
      .detail-group-title { font-size:10px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; margin-bottom:6px; }
      .detail-group-title.broken { color:#DC2626; }
      .detail-group-title.missing { color:#B45309; }
      .detail-group-title.params  { color:#64748B; }
      .iqa-path { font-family:monospace; font-size:11px; color:#5A7A9A; margin-bottom:3px; }
      .iqa-path.broken  { color:#DC2626; }
      .iqa-path.missing { color:#B45309; }
      .no-issues { font-size:11px; color:#8A9FBA; padding:4px 0; }
    </style>
    """

    IQA_EXPAND_JS = """
    <script>
      document.querySelectorAll('.iqa-row').forEach(function(row) {
        row.addEventListener('click', function() {
          var id = this.dataset.id;
          var detail = document.getElementById('detail-' + id);
          if (!detail) return;
          this.classList.toggle('open');
          detail.classList.toggle('open');
        });
      });
    </script>
    """

    rows_html = ""
    for i, r in enumerate(sorted_iqa):
        env    = escape(r.get("environment", "—"))
        status = r.get("status", "—")
        issues = r.get("issues_count", 0)
        ts     = escape(fmt_ts(r.get("checked_at")))
        details = r.get("details") or {}
        broken  = details.get("broken", [])
        missing = details.get("missing", [])
        params  = details.get("params", [])
        params_issue = issues > 0 and not broken and not missing and params
        has_details = bool(broken or missing or params_issue)
        chevron = '<span class="chevron">▶</span>' if has_details else '<span style="display:inline-block;width:16px;margin-right:6px"></span>'

        rows_html += f"""<tr class="iqa-row" data-id="{i}">
          <td><span class="env">{chevron}{env}</span></td>
          <td>{table_badge(status)}</td>
          <td><span class="cnt">{issues if issues else "—"}</span></td>
          <td><span class="ts">{ts}</span></td>
        </tr>"""

        # Detail row (always rendered, toggled via JS)
        if has_details:
            detail_html = '<div class="detail-inner">'
            if broken:
                detail_html += '<div class="detail-group">'
                detail_html += '<div class="detail-group-title broken">Broken</div>'
                for p in broken:
                    detail_html += f'<div class="iqa-path broken">{escape(p)}</div>'
                detail_html += '</div>'
            if missing:
                detail_html += '<div class="detail-group">'
                detail_html += '<div class="detail-group-title missing">Missing</div>'
                for p in missing:
                    detail_html += f'<div class="iqa-path missing">{escape(p)}</div>'
                detail_html += '</div>'
            if params_issue:
                detail_html += '<div class="detail-group">'
                detail_html += '<div class="detail-group-title params">Unexpected Params</div>'
                for p in params:
                    detail_html += f'<div class="iqa-path params">{escape(p)}</div>'
                detail_html += '</div>'
            detail_html += '</div>'
        else:
            detail_html = '<div class="no-issues">No issues found.</div>'

        rows_html += f"""<tr class="detail-row" id="detail-{i}">
          <td class="detail-cell" colspan="4">{detail_html}</td>
        </tr>"""

    # Estimate height: base rows + potential expanded detail rows (show up to 4 paths per env)
    height = 60 + len(sorted_iqa) * 42
    components.html(f"""{TABLE_CSS}{IQA_EXPAND_CSS}
    <div class="table-wrap">
      <table>
        <thead><tr><th>Environment</th><th>Status</th><th>Issues</th><th>Last Checked</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    {IQA_EXPAND_JS}""", height=height, scrolling=True)

# ── Section 3: Business Objects table ────────────────────────────────────────

st.markdown("<hr class='ds-divider'><div class='section-label'>Business Objects</div>", unsafe_allow_html=True)

if not bo_rows:
    st.info("No BO data yet. Run the BO Healthcheck to populate.")
else:
    sorted_bo = sorted(
        bo_rows,
        key=lambda r: ({"OK":2,"ISSUES":1,"DOWN":0}.get((r.get("status") or "DOWN").upper(), 0), r.get("environment","")),
        reverse=True
    )

    BO_EXPAND_JS = """
    <script>
      document.querySelectorAll('.bo-row').forEach(function(row) {
        row.addEventListener('click', function() {
          var id = this.dataset.id;
          var detail = document.getElementById('bo-detail-' + id);
          if (!detail) return;
          this.classList.toggle('open');
          detail.classList.toggle('open');
        });
      });
    </script>
    """

    rows_html = ""
    for i, r in enumerate(sorted_bo):
        env    = escape(r.get("environment", "—"))
        status = r.get("status", "—")
        issues = r.get("issues_count", 0)
        ts     = escape(fmt_ts(r.get("checked_at")))
        details = r.get("details") or {}
        missing = details.get("missing", [])
        broken  = details.get("broken", [])
        has_details = bool(missing or broken)
        chevron = '<span class="chevron">▶</span>' if has_details else '<span style="display:inline-block;width:16px;margin-right:6px"></span>'

        rows_html += f"""<tr class="iqa-row bo-row" data-id="{i}">
          <td><span class="env">{chevron}{env}</span></td>
          <td>{table_badge(status)}</td>
          <td><span class="cnt">{issues if issues else "—"}</span></td>
          <td><span class="ts">{ts}</span></td>
        </tr>"""

        if has_details:
            detail_html = '<div class="detail-inner">'
            if missing:
                detail_html += '<div class="detail-group"><div class="detail-group-title missing">Missing</div>'
                for bo in missing:
                    detail_html += f'<div class="iqa-path missing">{escape(bo)}</div>'
                detail_html += '</div>'
            if broken:
                detail_html += '<div class="detail-group"><div class="detail-group-title broken">Broken</div>'
                for bo in broken:
                    detail_html += f'<div class="iqa-path broken">{escape(bo)}</div>'
                detail_html += '</div>'
            detail_html += '</div>'
        else:
            detail_html = '<div class="no-issues">All BOs present.</div>'

        rows_html += f"""<tr class="detail-row" id="bo-detail-{i}">
          <td class="detail-cell" colspan="4">{detail_html}</td>
        </tr>"""

    height = 60 + len(sorted_bo) * 42
    components.html(f"""{TABLE_CSS}{IQA_EXPAND_CSS}
    <div class="table-wrap">
      <table>
        <thead><tr><th>Environment</th><th>Status</th><th>Issues</th><th>Last Checked</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    {BO_EXPAND_JS}""", height=height, scrolling=True)

# ── Section 5: Profile table ──────────────────────────────────────────────────

st.markdown("<hr class='ds-divider'><div class='section-label'>Profile Checks</div>", unsafe_allow_html=True)

if not profile_rows:
    st.info("No profile check data yet. Run the Profile Tester to populate.")
else:
    sorted_profiles = sorted(
        profile_rows,
        key=lambda r: ({"PASS":1,"FAIL":0}.get((r.get("status") or "FAIL").upper(), 0), r.get("environment","")),
        reverse=True
    )
    rows_html = ""
    for r in sorted_profiles:
        env    = escape(r.get("environment", "—"))
        status = r.get("status", "—")
        dur    = r.get("duration_seconds")
        dur_s  = f"{dur:.1f}s" if dur is not None else "—"
        ts     = escape(fmt_ts(r.get("checked_at")))
        error  = escape(r.get("error") or "")
        rows_html += f"""<tr>
          <td><span class="env">{env}</span></td>
          <td>{table_badge(status)}</td>
          <td><span class="ts">{dur_s}</span></td>
          <td><span class="ts">{ts}</span></td>
          <td><span class="err" title="{error}">{"" if not error or status.upper()=="PASS" else error[:60]}</span></td>
        </tr>"""

    height = 60 + len(sorted_profiles) * 42
    components.html(f"""{TABLE_CSS}
    <div class="table-wrap">
      <table>
        <thead><tr><th>Environment</th><th>Status</th><th>Duration</th><th>Last Checked</th><th>Error</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>""", height=height, scrolling=False)

# ── Section 6: Engage table ───────────────────────────────────────────────────

st.markdown("<hr class='ds-divider'><div class='section-label'>Engage</div>", unsafe_allow_html=True)

if not engage_rows:
    st.info("No Engage data yet. Run the Engage Healthcheck to populate.")
else:
    sorted_engage = sorted(
        engage_rows,
        key=lambda r: ({"OK": 2, "SLOW": 1, "DEGRADED": 1, "PARTIAL": 1, "DOWN": 0}.get((r.get("status") or "DOWN").upper(), 0), r.get("org", "")),
        reverse=True,
    )
    rows_html = ""
    for r in sorted_engage:
        org     = escape(r.get("org", "—"))
        status  = r.get("status", "—")
        load    = r.get("load_time_seconds")
        load_s  = f"{load:.1f}s" if load is not None else "—"
        ts      = escape(fmt_ts(r.get("checked_at")))
        c_err   = r.get("console_error_count") or 0
        p_err   = r.get("page_error_count") or 0
        summary = escape(r.get("errors_summary") or r.get("error_reason") or "")
        err_counts = ""
        if c_err:
            err_counts += f'<span style="color:#F59E0B;font-size:11px;margin-right:6px">⚠ {c_err} console</span>'
        if p_err:
            err_counts += f'<span style="color:#EF4444;font-size:11px;margin-right:6px">✕ {p_err} JS</span>'
        rows_html += f"""<tr>
          <td><span class="env">{org}</span></td>
          <td>{table_badge(status)}</td>
          <td><span class="ts">{load_s}</span></td>
          <td>{err_counts}</td>
          <td><span class="err" title="{summary}">{"" if not summary or status.upper() == "OK" else summary[:70]}</span></td>
          <td><span class="ts">{ts}</span></td>
        </tr>"""

    height = 60 + len(sorted_engage) * 42
    components.html(f"""{TABLE_CSS}
    <div class="table-wrap">
      <table>
        <thead><tr><th>Org</th><th>Status</th><th>Load</th><th>Errors</th><th>Details</th><th>Last Checked</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>""", height=height, scrolling=False)

# ── Section 7: Algolia table ─────────────────────────────────────────────────

st.markdown("<hr class='ds-divider'><div class='section-label'>Algolia</div>", unsafe_allow_html=True)

if not algolia_rows:
    st.info("No Algolia data yet. Run the Algolia Healthcheck to populate.")
else:
    sorted_algolia = sorted(
        algolia_rows,
        key=lambda r: ({"OK":3,"NO_KEY":2,"AUTH_ERROR":1,"DOWN":0,"ERROR":0}.get((r.get("status") or "DOWN").upper(), 0), r.get("environment","")),
        reverse=True
    )
    rows_html = ""
    for r in sorted_algolia:
        env    = escape(r.get("environment", "—"))
        status = r.get("status", "—")
        app_id = escape(r.get("app_id") or "—")
        ts     = escape(fmt_ts(r.get("checked_at")))
        error  = escape(r.get("error") or "")
        rows_html += f"""<tr>
          <td><span class="env">{env}</span></td>
          <td><span style="font-family:monospace;font-size:11px;color:#5A7A9A;">{app_id}</span></td>
          <td>{table_badge(status)}</td>
          <td><span class="err" title="{error}">{"" if not error or status.upper() == "OK" else error[:60]}</span></td>
          <td><span class="ts">{ts}</span></td>
        </tr>"""

    height = 60 + len(sorted_algolia) * 42
    components.html(f"""{TABLE_CSS}
    <div class="table-wrap">
      <table>
        <thead><tr><th>Environment</th><th>App ID</th><th>Status</th><th>Error</th><th>Last Checked</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>""", height=height, scrolling=False)

# ── Footer ────────────────────────────────────────────────────────────────────

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
st.markdown(f"""
<hr class="ds-divider">
<p style="font-size:11px;color:#334155;text-align:center;margin-top:1.5rem;">
  DataScout Ops &nbsp;·&nbsp; Refreshed {now} &nbsp;·&nbsp; Data cached 2 min
</p>""", unsafe_allow_html=True)
