"""
DataScout Ops Dashboard
Run: python3 -m streamlit run dashboard.py
"""

import os
from datetime import datetime, timezone, timedelta

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="DataScout Ops",
    page_icon="🛰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; background-color: #020617; color: #F8FAFC; }
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding: 2rem 2rem 4rem; max-width: 1400px; }
  .section-label { font-size:11px; font-weight:600; letter-spacing:0.1em; text-transform:uppercase; color:#475569; margin-bottom:0.75rem; margin-top:2rem; }
  .pill-row { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:1.5rem; }
  .pill { padding:4px 14px; border-radius:999px; font-size:12px; font-weight:600; }
  .pill-green  { background:#14532d; color:#22C55E; }
  .pill-amber  { background:#451a03; color:#F59E0B; }
  .pill-red    { background:#450a0a; color:#EF4444; }
  .pill-gray   { background:#1E293B; color:#94A3B8; }
  .bot-card { background:#0F172A; border:1px solid #1E293B; border-radius:10px; padding:14px 16px; margin-bottom:10px; }
  .bot-card.up       { border-left:3px solid #22C55E; }
  .bot-card.degraded { border-left:3px solid #F59E0B; }
  .bot-card.down     { border-left:3px solid #EF4444; }
  .bot-name { font-size:13px; font-weight:600; color:#F8FAFC; margin-bottom:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .bot-badge { display:inline-block; font-size:10px; font-weight:700; padding:2px 8px; border-radius:999px; letter-spacing:0.05em; margin-bottom:8px; }
  .badge-up       { background:#14532d; color:#22C55E; }
  .badge-degraded { background:#451a03; color:#F59E0B; }
  .badge-down     { background:#450a0a; color:#EF4444; }
  .bot-meta { font-size:11px; color:#64748B; display:flex; gap:10px; flex-wrap:wrap; }
  .last-checked { font-size:11px; color:#475569; margin-top:5px; }
  .ds-divider { border:none; border-top:1px solid #1E293B; margin:2rem 0 0; }
</style>
""", unsafe_allow_html=True)

# ── Table CSS (used inside components.html) ──────────────────────────────────

TABLE_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: transparent; font-family: 'Inter', sans-serif; }
  .table-wrap { background:#0F172A; border:1px solid #1E293B; border-radius:10px; overflow:hidden; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; padding:9px 14px; color:#475569; font-weight:500; font-size:11px; text-transform:uppercase; letter-spacing:0.05em; border-bottom:1px solid #1E293B; }
  td { padding:10px 14px; border-bottom:1px solid #1E293B; color:#F8FAFC; vertical-align:middle; }
  tr:last-child td { border-bottom:none; }
  tr:hover td { background:#131f35; }
  .env  { font-weight:600; color:#60A5FA; font-family:monospace; font-size:12px; }
  .ts   { color:#475569; font-size:11px; }
  .err  { color:#EF4444; font-size:11px; max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .cnt  { color:#94A3B8; font-size:12px; }
  .s-ok      { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#14532d; color:#22C55E; }
  .s-issues  { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#451a03; color:#F59E0B; }
  .s-down    { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#450a0a; color:#EF4444; }
  .s-pass    { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#14532d; color:#22C55E; }
  .s-fail    { display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; background:#450a0a; color:#EF4444; }
  .uptime-badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:700; }
  .uptime-cell { display:flex; flex-direction:column; gap:4px; }
</style>
"""

# ── Supabase ─────────────────────────────────────────────────────────────────

PRODUCTION_ENVS = {"aaae", "aboncle", "oasw", "cpanb"}

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

@st.cache_data(ttl=300)
def fetch_history(table: str, env_col: str, days: int = 30) -> list[dict]:
    sb = get_supabase()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    res = sb.table(table).select(f"{env_col},status,checked_at").gte("checked_at", since).execute()
    return res.data


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_ts(iso):
    if not iso:
        return "—"
    try:
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
    css = {"OK":"s-ok","ISSUES":"s-issues","DOWN":"s-down","PASS":"s-pass","FAIL":"s-fail"}.get(s,"s-down")
    return f'<span class="{css}">{s}</span>'

def count_statuses(rows, field, values):
    vals = [v.upper() for v in values]
    return sum(1 for r in rows if (r.get(field) or "").upper() in vals)

def escape(s):
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def compute_uptime(rows: list[dict], env_col: str, good_statuses: list[str]) -> dict[str, float]:
    good_set = {s.upper() for s in good_statuses}
    counts: dict[str, list[int]] = {}
    for row in rows:
        env = row.get(env_col)
        if not env:
            continue
        status = (row.get("status") or "").upper()
        if env not in counts:
            counts[env] = [0, 0]
        counts[env][1] += 1
        if status in good_set:
            counts[env][0] += 1
    return {env: (g / t * 100 if t > 0 else 0.0) for env, (g, t) in counts.items()}

def uptime_badge(pct: float | None) -> str:
    if pct is None:
        return '<span style="font-size:10px;color:#475569;">—</span>'
    color, bg = ("#22C55E","#14532d") if pct >= 95 else ("#F59E0B","#451a03") if pct >= 80 else ("#EF4444","#450a0a")
    return f'<span class="uptime-badge" style="background:{bg};color:{color};">{pct:.1f}%</span>'

def daily_uptime(rows: list[dict], env_col: str, env_name: str, good_statuses: list[str], days: int = 7) -> list[float | None]:
    from datetime import date as date_t
    good_set = {s.upper() for s in good_statuses}
    today = datetime.now(timezone.utc).date()
    day_counts: dict[date_t, list[int]] = {}
    for row in rows:
        if row.get(env_col) != env_name:
            continue
        ts = row.get("checked_at")
        if not ts:
            continue
        try:
            d = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
        except Exception:
            continue
        status = (row.get("status") or "").upper()
        if d not in day_counts:
            day_counts[d] = [0, 0]
        day_counts[d][1] += 1
        if status in good_set:
            day_counts[d][0] += 1
    result = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        if d in day_counts and day_counts[d][1] > 0:
            g, t = day_counts[d]
            result.append(g / t * 100)
        else:
            result.append(None)
    return result

def sparkline_svg(data: list[float | None], width: int = 60, height: int = 18) -> str:
    n = len(data)
    bar_w = max(1, (width - (n - 1) * 2) // n)
    bars = ""
    for i, pct in enumerate(data):
        x = i * (bar_w + 2)
        if pct is None:
            bars += f'<rect x="{x}" y="{height-4}" width="{bar_w}" height="4" rx="1" fill="#1E293B"/>'
        else:
            h = max(4, int(height * pct / 100))
            color = "#22C55E" if pct >= 95 else "#F59E0B" if pct >= 80 else "#EF4444"
            bars += f'<rect x="{x}" y="{height-h}" width="{bar_w}" height="{h}" rx="1" fill="{color}"/>'
    return f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="display:inline-block;vertical-align:middle;">{bars}</svg>'

def prod_sla(iqa_up: dict, prof_up: dict) -> float | None:
    vals = [v for env in PRODUCTION_ENVS for v in [iqa_up.get(env), prof_up.get(env)] if v is not None]
    return sum(vals) / len(vals) if vals else None


# ── Header ────────────────────────────────────────────────────────────────────

col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.markdown("""
        <h1 style="font-size:26px;font-weight:700;color:#F8FAFC;margin:0;letter-spacing:-0.5px;">DataScout Ops Dashboard</h1>
        <p style="font-size:13px;color:#475569;margin:6px 0 0;">Platform health across all environments</p>
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
    conc_history   = fetch_history("concierge_checks", "name", days=30)
    iqa_history    = fetch_history("iqa_checks", "environment", days=30)
    prof_history   = fetch_history("profile_checks", "environment", days=30)

conc_uptime = compute_uptime(conc_history, "name", ["UP"])
iqa_uptime  = compute_uptime(iqa_history, "environment", ["OK"])
prof_uptime = compute_uptime(prof_history, "environment", ["PASS"])

# ── Summary cards ─────────────────────────────────────────────────────────────

c_up       = count_statuses(concierge_rows, "status", ["UP"])
c_degraded = count_statuses(concierge_rows, "status", ["DEGRADED"])
c_down     = count_statuses(concierge_rows, "status", ["DOWN"])
i_ok       = count_statuses(iqa_rows, "status", ["OK"])
i_issues   = count_statuses(iqa_rows, "status", ["ISSUES"])
i_down     = count_statuses(iqa_rows, "status", ["DOWN"])
p_pass     = count_statuses(profile_rows, "status", ["PASS"])
p_fail     = count_statuses(profile_rows, "status", ["FAIL"])

def latest_ts(rows):
    ts = max((r.get("checked_at") or "" for r in rows), default="")
    return fmt_ts(ts) if ts else "—"

def summary_card(title, icon, main_val, main_label, main_color, sub_items, last_checked):
    subs = "".join([
        f'<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #1E293B;">'
        f'<span style="font-size:13px;color:#94A3B8;font-weight:500;">{label}</span>'
        f'<span style="font-size:15px;font-weight:700;color:{color};">{val}</span>'
        f'</div>'
        for val, label, color in sub_items
    ])
    return f"""
    <div style="background:#0F172A;border:1px solid #1E293B;border-radius:14px;padding:24px 28px;height:100%;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;">
        <span style="font-size:20px;">{icon}</span>
        <span style="font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#64748B;">{title}</span>
      </div>
      <div style="font-size:52px;font-weight:800;color:{main_color};line-height:1;letter-spacing:-2px;">{main_val}</div>
      <div style="font-size:13px;color:#64748B;margin-top:6px;font-weight:400;">{main_label}</div>
      <div style="border-top:1px solid #1E293B;margin-top:20px;">{subs}</div>
      <div style="margin-top:16px;display:flex;align-items:center;gap:6px;">
        <span style="width:6px;height:6px;border-radius:50%;background:#22C55E;display:inline-block;flex-shrink:0;"></span>
        <span style="font-size:12px;color:#94A3B8;">Last checked <strong style="color:#CBD5E1;">{last_checked}</strong></span>
      </div>
    </div>"""

sla = prod_sla(iqa_uptime, prof_uptime)
sla_str   = f"{sla:.1f}%" if sla is not None else "—"
sla_color = "#22C55E" if sla and sla >= 95 else "#F59E0B" if sla and sla >= 80 else "#EF4444"
prod_ok   = sum(1 for e in PRODUCTION_ENVS if iqa_uptime.get(e, 0) >= 95)

c1, c2, c3, c4 = st.columns(4)
with c1:
    c_total = c_up + c_degraded + c_down
    st.markdown(summary_card(
        "Concierge Bots", "🤖",
        c_up, f"of {c_total} bots online", "#22C55E",
        [(c_degraded, "Degraded", "#F59E0B"), (c_down, "Down", "#EF4444")],
        latest_ts(concierge_rows)
    ), unsafe_allow_html=True)
with c2:
    i_total = i_ok + i_issues + i_down
    st.markdown(summary_card(
        "IQA Structure", "🔍",
        i_ok, f"of {i_total} environments OK", "#22C55E",
        [(i_issues, "With issues", "#F59E0B"), (i_down, "Down", "#EF4444")],
        latest_ts(iqa_rows)
    ), unsafe_allow_html=True)
with c3:
    p_total = p_pass + p_fail
    st.markdown(summary_card(
        "Profile Checks", "👤",
        p_pass, f"of {p_total} environments passing", "#22C55E",
        [(p_fail, "Failing", "#EF4444")],
        latest_ts(profile_rows)
    ), unsafe_allow_html=True)
with c4:
    st.markdown(summary_card(
        "Production SLA", "📊",
        sla_str, "avg uptime · 30 days", sla_color,
        [(f"{prod_ok}/{len(PRODUCTION_ENVS)}", "Envs ≥ 95% uptime", "#22C55E")],
        "30-day window"
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
        name    = bot.get("name", "—")
        status  = bot.get("status", "DOWN")
        sc      = status_class(status)
        bc      = badge_class(status)
        http    = fmt_ms(bot.get("http_response_ms"))
        chat    = fmt_ms(bot.get("chat_response_ms"))
        ts      = fmt_ts(bot.get("checked_at"))
        error   = escape(bot.get("error") or "")
        up_pct  = conc_uptime.get(name)
        up_str  = f"{up_pct:.0f}% up" if up_pct is not None else ""
        with cols[i % 5]:
            st.markdown(f"""
            <div class="bot-card {sc}">
              <div class="bot-name" title="{escape(name)}">{escape(name)}</div>
              <div><span class="bot-badge {bc}">{escape(status)}</span></div>
              <div class="bot-meta">
                <span>HTTP {http}</span><span>Chat {chat}</span>
                {"" if not up_str else f'<span style="color:#64748B;">{up_str} (30d)</span>'}
              </div>
              {"" if not error or sc == "up" else f'<div style="font-size:10px;color:#EF4444;margin-top:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{error[:50]}</div>'}
              <div class="last-checked">{ts}</div>
            </div>""", unsafe_allow_html=True)

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
      .iqa-row:hover td { background: #1a2740 !important; }
      .iqa-row td:first-child .chevron { display:inline-block; margin-right:6px; color:#475569; font-size:10px; transition:transform 0.2s; }
      .iqa-row.open td:first-child .chevron { transform: rotate(90deg); color:#60A5FA; }
      .detail-row { display:none; }
      .detail-row.open { display:table-row; }
      .detail-cell { padding:0 14px 12px 32px !important; border-bottom:1px solid #1E293B; background:#0a1120 !important; }
      .detail-inner { display:flex; gap:24px; flex-wrap:wrap; padding-top:8px; }
      .detail-group { min-width:180px; }
      .detail-group-title { font-size:10px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; margin-bottom:6px; }
      .detail-group-title.broken { color:#EF4444; }
      .detail-group-title.missing { color:#F59E0B; }
      .detail-group-title.params  { color:#64748B; }
      .iqa-path { font-family:monospace; font-size:11px; color:#94A3B8; margin-bottom:3px; }
      .iqa-path.broken  { color:#FCA5A5; }
      .iqa-path.missing { color:#FCD34D; }
      .no-issues { font-size:11px; color:#475569; padding:4px 0; }
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
        env_name = r.get("environment", "—")
        env      = escape(env_name)
        status   = r.get("status", "—")
        issues   = r.get("issues_count", 0)
        ts       = escape(fmt_ts(r.get("checked_at")))
        details  = r.get("details") or {}
        broken   = details.get("broken", [])
        missing  = details.get("missing", [])
        has_details = bool(broken or missing)
        chevron  = '<span class="chevron">▶</span>' if has_details else '<span style="display:inline-block;width:16px;margin-right:6px"></span>'

        up_pct   = iqa_uptime.get(env_name)
        spark    = daily_uptime(iqa_history, "environment", env_name, ["OK"])
        uptime_cell = f'<div class="uptime-cell">{uptime_badge(up_pct)}{sparkline_svg(spark)}</div>'

        rows_html += f"""<tr class="iqa-row" data-id="{i}">
          <td><span class="env">{chevron}{env}</span></td>
          <td>{table_badge(status)}</td>
          <td><span class="cnt">{issues if issues else "—"}</span></td>
          <td>{uptime_cell}</td>
          <td><span class="ts">{ts}</span></td>
        </tr>"""

        if has_details:
            detail_html = '<div class="detail-inner">'
            if broken:
                detail_html += '<div class="detail-group"><div class="detail-group-title broken">Broken</div>'
                for p in broken:
                    detail_html += f'<div class="iqa-path broken">{escape(p)}</div>'
                detail_html += '</div>'
            if missing:
                detail_html += '<div class="detail-group"><div class="detail-group-title missing">Missing</div>'
                for p in missing:
                    detail_html += f'<div class="iqa-path missing">{escape(p)}</div>'
                detail_html += '</div>'
            detail_html += '</div>'
        else:
            detail_html = '<div class="no-issues">No broken or missing IQAs.</div>'

        rows_html += f"""<tr class="detail-row" id="detail-{i}">
          <td class="detail-cell" colspan="5">{detail_html}</td>
        </tr>"""

    height = 60 + len(sorted_iqa) * 44
    components.html(f"""{TABLE_CSS}{IQA_EXPAND_CSS}
    <div class="table-wrap">
      <table>
        <thead><tr><th>Environment</th><th>Status</th><th>Issues</th><th>Uptime 30d</th><th>Last Checked</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    {IQA_EXPAND_JS}""", height=height, scrolling=True)

# ── Section 3: Profile table ──────────────────────────────────────────────────

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
        env_name = r.get("environment", "—")
        env      = escape(env_name)
        status   = r.get("status", "—")
        dur      = r.get("duration_seconds")
        dur_s    = f"{dur:.1f}s" if dur is not None else "—"
        ts       = escape(fmt_ts(r.get("checked_at")))
        error    = escape(r.get("error") or "")
        up_pct   = prof_uptime.get(env_name)
        spark    = daily_uptime(prof_history, "environment", env_name, ["PASS"])
        uptime_cell = f'<div class="uptime-cell">{uptime_badge(up_pct)}{sparkline_svg(spark)}</div>'
        rows_html += f"""<tr>
          <td><span class="env">{env}</span></td>
          <td>{table_badge(status)}</td>
          <td><span class="ts">{dur_s}</span></td>
          <td>{uptime_cell}</td>
          <td><span class="ts">{ts}</span></td>
          <td><span class="err" title="{error}">{"" if not error or status.upper()=="PASS" else error[:60]}</span></td>
        </tr>"""

    height = 60 + len(sorted_profiles) * 44
    components.html(f"""{TABLE_CSS}
    <div class="table-wrap">
      <table>
        <thead><tr><th>Environment</th><th>Status</th><th>Duration</th><th>Uptime 30d</th><th>Last Checked</th><th>Error</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>""", height=height, scrolling=False)

# ── Footer ────────────────────────────────────────────────────────────────────

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
st.markdown(f"""
<hr class="ds-divider">
<p style="font-size:11px;color:#334155;text-align:center;margin-top:1.5rem;">
  DataScout Ops &nbsp;·&nbsp; Refreshed {now} &nbsp;·&nbsp; Live data cached 2 min · Uptime cached 5 min
</p>""", unsafe_allow_html=True)
