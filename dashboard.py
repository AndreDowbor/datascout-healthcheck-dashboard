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
  html, body, [class*="css"] { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #FFF8F4; color: #0D1B3E; }
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
  .bot-meta span:not(:last-child) { margin-right:10px; }
  .last-checked { font-size:11px; color:#8A9FBA; margin-top:5px; }
  .ds-divider { border:none; border-top:1px solid #F0D8C8; margin:2rem 0 0; }
  div[data-testid="stTextInput"] input { border-radius:10px; border:1px solid #F0D8C8; padding:10px 14px; font-size:13px; }
  div[data-testid="stTextInput"] input:focus { border-color:#FC6305 !important; box-shadow:0 0 0 1px #FC6305 !important; }
  .known-tag { display:inline-block; font-size:9px; font-weight:700; padding:1px 7px; border-radius:999px; letter-spacing:0.04em; margin-left:6px; background:#E2E8F0; color:#64748B; border:1px dashed #94A3B8; text-transform:uppercase; vertical-align:middle; }
  .trend-tag { display:inline-block; font-size:9px; font-weight:700; padding:1px 7px; border-radius:999px; letter-spacing:0.03em; margin-left:6px; vertical-align:middle; }
  .trend-new { background:#FEE2E2; color:#DC2626; }
  .trend-recurring { background:#F1F5F9; color:#94A3B8; }
</style>
""", unsafe_allow_html=True)

# ── Table CSS (used inside components.html) ──────────────────────────────────

TABLE_CSS = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: transparent; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
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
  .known-tag { display:inline-block; font-size:9px; font-weight:700; padding:1px 7px; border-radius:999px; letter-spacing:0.04em; margin-left:6px; background:#E2E8F0; color:#64748B; border:1px dashed #94A3B8; text-transform:uppercase; vertical-align:middle; }
  .trend-tag { display:inline-block; font-size:9px; font-weight:700; padding:1px 7px; border-radius:999px; letter-spacing:0.03em; margin-left:6px; vertical-align:middle; }
  .trend-new { background:#FEE2E2; color:#DC2626; }
  .trend-recurring { background:#F1F5F9; color:#94A3B8; }
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
def fetch_latest(table: str, group_col: str, limit: int = 500, max_age_hours: int = 48) -> list[dict]:
    from datetime import timedelta
    sb = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    res = (
        sb.table(table)
        .select("*")
        .gte("checked_at", cutoff)
        .order("checked_at", desc=True)
        .limit(limit)
        .execute()
    )
    seen = {}
    previous_status = {}
    for row in res.data:
        # Include "url" in the key: some tables (e.g. concierge_checks) reuse
        # the same name/environment for two distinct check variants (direct
        # chat URL vs. iMIS member-login flow), which would otherwise collide
        # and silently drop one of the two checks. There's no "type" column
        # to disambiguate on, but the url always differs between variants.
        # Also include "environment" (prod/staging): engage_checks reuses
        # identical org names between the two (e.g. NTEU, CPA NB), which
        # would otherwise collide and silently drop one of the two rows.
        key = (row.get(group_col), row.get("url"), row.get("environment"))
        if key not in seen:
            seen[key] = row
        elif key not in previous_status:
            # Second time we see this key = the next-most-recent check for
            # the same env/org/bot, since res.data is ordered by checked_at
            # desc. Stash it so the UI can show "new failure" vs "recurring".
            previous_status[key] = row.get("status")
    result = list(seen.values())
    for row in result:
        key = (row.get(group_col), row.get("url"), row.get("environment"))
        row["_previous_status"] = previous_status.get(key)
    return result


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
    # startswith (not exact equality) because some statuses carry a reason
    # suffix, e.g. "DEGRADED (no-widget)" should still count as "DEGRADED".
    vals = [v.upper() for v in values]
    return sum(1 for r in rows if (r.get(field) or "").upper().startswith(tuple(vals)))

def escape(s):
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

# Environments known to be failing for a reason already tracked outside this
# dashboard (e.g. a partner conversation in progress) — tagged so they don't
# read as a new/urgent finding every time someone glances at the board.
KNOWN_ISSUE_ENVS = {
    "atdemo81": "Likely discontinued partner environment — partner already notified, decision pending. Not a new bug.",
}

def known_tag(name):
    note = KNOWN_ISSUE_ENVS.get((name or "").strip().lower())
    if not note:
        return ""
    return f'<span class="known-tag" title="{escape(note)}">known issue</span>'

_GOOD_STATUS_PREFIXES = ("OK", "PASS", "UP", "SKIP", "NO_KEY")

def _is_bad_status(status):
    s = (status or "").upper()
    return bool(s) and not s.startswith(_GOOD_STATUS_PREFIXES)

def trend_tag(status, previous_status):
    """Flags a failing row as newly-broken vs. still-broken-since-last-check."""
    if not _is_bad_status(status) or not previous_status:
        return ""
    if _is_bad_status(previous_status):
        return '<span class="trend-tag trend-recurring" title="Also failed on the previous check">↻ recurring</span>'
    return '<span class="trend-tag trend-new" title="Passed on the previous check — this just started failing">✦ new</span>'


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
# engage_checks covers two distinct target lists (production orgs vs. staging
# partner/demo orgs) that can share the exact same org name (NTEU, CPA NB
# appear in both) — split by the "environment" column rather than treating
# it as one pool, or the two get silently conflated in both the count and
# the table below.
engage_prod_rows    = [r for r in engage_rows if r.get("environment") == "production"]
engage_staging_rows = [r for r in engage_rows if r.get("environment") == "staging"]
ep_ok      = count_statuses(engage_prod_rows, "status", ["OK"])
ep_slow    = count_statuses(engage_prod_rows, "status", ["SLOW", "PARTIAL", "DEGRADED"])
ep_down    = count_statuses(engage_prod_rows, "status", ["DOWN"])
es_ok      = count_statuses(engage_staging_rows, "status", ["OK"])
es_slow    = count_statuses(engage_staging_rows, "status", ["SLOW", "PARTIAL", "DEGRADED"])
es_down    = count_statuses(engage_staging_rows, "status", ["DOWN"])
a_ok       = count_statuses(algolia_rows, "status", ["OK"])
a_warn     = count_statuses(algolia_rows, "status", ["AUTH_ERROR", "NO_KEY", "SKIP"])
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

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
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
    ep_total = ep_ok + ep_slow + ep_down
    st.markdown(summary_card(
        "Engage — Prod", "⚡",
        ep_ok, f"of {ep_total} orgs OK", "#16A34A",
        [(ep_slow, "Slow", "#D97706"), (ep_down, "Down", "#DC2626")],
        latest_ts(engage_prod_rows)
    ), unsafe_allow_html=True)
with c6:
    es_total = es_ok + es_slow + es_down
    st.markdown(summary_card(
        "Engage — Staging", "⚡",
        es_ok, f"of {es_total} orgs OK", "#16A34A",
        [(es_slow, "Slow", "#D97706"), (es_down, "Down", "#DC2626")],
        latest_ts(engage_staging_rows)
    ), unsafe_allow_html=True)
with c7:
    a_total = a_ok + a_warn + a_down
    st.markdown(summary_card(
        "Algolia", "🔎",
        a_ok, f"of {a_total} apps OK", "#16A34A",
        [(a_warn, "Auth / No key", "#D97706"), (a_down, "Down", "#DC2626")],
        latest_ts(algolia_rows)
    ), unsafe_allow_html=True)

st.markdown("<div style='margin-top:2rem'></div>", unsafe_allow_html=True)

# ── Search / filter ──────────────────────────────────────────────────────────
# Filters the per-section lists below (bot cards + all tables) by name/env/org
# substring. Summary cards above intentionally stay unfiltered — they should
# always reflect the whole fleet, not just the current search.

search_query = st.text_input(
    "Filter",
    placeholder="🔍  Filter by environment, org, or bot name…",
    label_visibility="collapsed",
    key="global_search",
).strip().lower()

def _filter(rows, field):
    if not search_query:
        return rows
    return [r for r in rows if search_query in (r.get(field) or "").lower()]

def _section_empty(original_rows, filtered_rows, no_data_msg) -> bool:
    """Renders the right info message and returns True if the section should be skipped."""
    if not original_rows:
        st.info(no_data_msg)
        return True
    if not filtered_rows and search_query:
        st.info(f"No matches for “{search_query}”.")
        return True
    return False

concierge_rows_f      = _filter(concierge_rows, "name")
iqa_rows_f             = _filter(iqa_rows, "environment")
bo_rows_f              = _filter(bo_rows, "environment")
profile_rows_f         = _filter(profile_rows, "environment")
engage_prod_rows_f     = _filter(engage_prod_rows, "org")
engage_staging_rows_f  = _filter(engage_staging_rows, "org")
algolia_rows_f         = _filter(algolia_rows, "environment")

st.markdown("<div style='margin-top:0.5rem'></div>", unsafe_allow_html=True)

# ── Section 1: Concierge bot cards ────────────────────────────────────────────

st.markdown('<div class="section-label">Concierge Bots</div>', unsafe_allow_html=True)

if _section_empty(concierge_rows, concierge_rows_f, "No concierge data yet."):
    pass
else:
    order = {"DOWN": 0, "DEGRADED": 1, "UP": 2}
    sorted_bots = sorted(
        concierge_rows_f,
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
            k_tag = known_tag(name)
            t_tag = trend_tag(status, bot.get("_previous_status"))
            card_inner = (
                f'<div class="bot-name" title="{escape(name)}">{escape(name)}</div>'
                f'<div><span class="bot-badge {bc}">{escape(status)}</span>{k_tag}{t_tag}</div>'
                f'<div class="bot-meta"><span>HTTP {http}</span><span>·&nbsp;Chat {chat}</span></div>'
                f'{error_html}'
                f'<div class="last-checked">{ts}</div>'
            )
            if url:
                st.markdown(f'<a class="bot-link" href="{url}" target="_blank" rel="noopener noreferrer"><div class="bot-card {sc}">{card_inner}</div></a>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bot-card {sc}">{card_inner}</div>', unsafe_allow_html=True)

# ── Section 2: IQA table ──────────────────────────────────────────────────────

st.markdown("<hr class='ds-divider'><div class='section-label'>IQA Structure</div>", unsafe_allow_html=True)

if _section_empty(iqa_rows, iqa_rows_f, "No IQA data yet."):
    pass
else:
    sorted_iqa = sorted(
        iqa_rows_f,
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
      .detail-group-title.errored { color:#7C3AED; }
      .iqa-path { font-family:monospace; font-size:11px; color:#5A7A9A; margin-bottom:3px; }
      .iqa-path.broken  { color:#DC2626; }
      .iqa-path.missing { color:#B45309; }
      .iqa-path.errored { color:#7C3AED; }
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
        k_tag = known_tag(r.get("environment"))
        t_tag = trend_tag(status, r.get("_previous_status"))

        rows_html += f"""<tr class="iqa-row" data-id="{i}">
          <td><span class="env">{chevron}{env}</span></td>
          <td>{table_badge(status)}{k_tag}{t_tag}</td>
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

if _section_empty(bo_rows, bo_rows_f, "No BO data yet. Run the BO Healthcheck to populate."):
    pass
else:
    sorted_bo = sorted(
        bo_rows_f,
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
        errored = details.get("errored", [])
        has_details = bool(missing or broken or errored)
        chevron = '<span class="chevron">▶</span>' if has_details else '<span style="display:inline-block;width:16px;margin-right:6px"></span>'
        k_tag = known_tag(r.get("environment"))
        t_tag = trend_tag(status, r.get("_previous_status"))

        rows_html += f"""<tr class="iqa-row bo-row" data-id="{i}">
          <td><span class="env">{chevron}{env}</span></td>
          <td>{table_badge(status)}{k_tag}{t_tag}</td>
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
            if errored:
                detail_html += '<div class="detail-group"><div class="detail-group-title errored">Timed Out / Error</div>'
                for bo in errored:
                    detail_html += f'<div class="iqa-path errored">{escape(bo)}</div>'
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

if _section_empty(profile_rows, profile_rows_f, "No profile check data yet. Run the Profile Tester to populate."):
    pass
else:
    sorted_profiles = sorted(
        profile_rows_f,
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
        k_tag  = known_tag(r.get("environment"))
        t_tag  = trend_tag(status, r.get("_previous_status"))
        rows_html += f"""<tr>
          <td><span class="env">{env}</span></td>
          <td>{table_badge(status)}{k_tag}{t_tag}</td>
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

# ── Section 6: Engage tables (Production / Staging) ──────────────────────────

def render_engage_table(original_rows, filtered_rows):
    if _section_empty(original_rows, filtered_rows, "No Engage data yet. Run the Engage Healthcheck to populate."):
        return
    sorted_engage = sorted(
        filtered_rows,
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
        k_tag = known_tag(r.get("org"))
        t_tag = trend_tag(status, r.get("_previous_status"))
        rows_html += f"""<tr>
          <td><span class="env">{org}</span></td>
          <td>{table_badge(status)}{k_tag}{t_tag}</td>
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

st.markdown("<hr class='ds-divider'><div class='section-label'>Engage — Production</div>", unsafe_allow_html=True)
render_engage_table(engage_prod_rows, engage_prod_rows_f)

st.markdown("<div class='section-label'>Engage — Staging</div>", unsafe_allow_html=True)
render_engage_table(engage_staging_rows, engage_staging_rows_f)

# ── Section 7: Algolia table ─────────────────────────────────────────────────

st.markdown("<hr class='ds-divider'><div class='section-label'>Algolia</div>", unsafe_allow_html=True)

if _section_empty(algolia_rows, algolia_rows_f, "No Algolia data yet. Run the Algolia Healthcheck to populate."):
    pass
else:
    sorted_algolia = sorted(
        algolia_rows_f,
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
        k_tag  = known_tag(r.get("environment"))
        t_tag  = trend_tag(status, r.get("_previous_status"))
        rows_html += f"""<tr>
          <td><span class="env">{env}</span></td>
          <td><span style="font-family:monospace;font-size:11px;color:#5A7A9A;">{app_id}</span></td>
          <td>{table_badge(status)}{k_tag}{t_tag}</td>
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
