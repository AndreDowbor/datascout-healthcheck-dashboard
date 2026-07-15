"""
dashboard.py — Local web dashboard for Chat Monitor.

Serves a live-updating status page at http://localhost:8080
Reads logs/monitor.log — no extra dependencies required.

Run: python3 dashboard.py
"""

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "monitor.log")
PORT = 8080


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------


def parse_log() -> tuple[dict, dict]:
    """
    Read the log file and return:
      - bots: {name: latest result dict}
      - cycle: latest cycle_complete dict (or empty)
    """
    bots: dict[str, dict] = {}
    cycle: dict = {}

    if not os.path.exists(LOG_PATH):
        return bots, cycle

    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("event") == "cycle_complete":
                cycle = entry
            elif "name" in entry and "status" in entry:
                bots[entry["name"]] = entry

    return bots, cycle


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------


STATUS_COLOR = {
    "UP": ("#16a34a", "#dcfce7", "✓"),
    "DEGRADED": ("#d97706", "#fef3c7", "⚠"),
    "DOWN": ("#dc2626", "#fee2e2", "✕"),
}


def _status_style(status: str) -> tuple[str, str, str]:
    if status == "UP":
        return STATUS_COLOR["UP"]
    if "DEGRADED" in status:
        return STATUS_COLOR["DEGRADED"]
    return STATUS_COLOR["DOWN"]


def _fmt_ms(ms: int | None) -> str:
    if ms is None:
        return "—"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms}ms"


def _fmt_ts(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso


def build_html(bots: dict, cycle: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = cycle.get("total", len(bots))
    up = cycle.get("up", sum(1 for b in bots.values() if b.get("status") == "UP"))
    degraded = cycle.get("degraded", 0)
    down = cycle.get("down", 0)
    last_cycle = _fmt_ts(cycle.get("timestamp"))

    overall_color = "#16a34a" if up == total else ("#d97706" if down == 0 else "#dc2626")

    cards_html = ""
    for name, bot in sorted(bots.items()):
        status = bot.get("status", "DOWN")
        fg, bg, icon = _status_style(status)
        http_ms = _fmt_ms(bot.get("http_response_ms"))
        chat_ms = _fmt_ms(bot.get("chat_response_ms"))
        response_text = (bot.get("chat_response_text") or "")[:80]
        error = bot.get("error") or ""
        url = bot.get("url", "")
        ts = _fmt_ts(bot.get("timestamp"))

        cards_html += f"""
        <div class="card" style="border-left: 4px solid {fg}; background: {bg};">
          <div class="card-header">
            <span class="bot-name">{name}</span>
            <span class="badge" style="background:{fg}; color:#fff;">{icon} {status}</span>
          </div>
          <div class="card-meta">
            <span title="HTTP response time">HTTP: {http_ms}</span>
            <span title="Chat response time">Chat: {chat_ms}</span>
          </div>
          {"<div class='response-text'>&ldquo;" + response_text + "&rdquo;</div>" if response_text else ""}
          {"<div class='error-text'>" + error + "</div>" if error and status != "UP" else ""}
          <div class="card-ts">{ts}</div>
        </div>"""

    no_data = "<p style='text-align:center;color:#6b7280;margin-top:3rem;'>No data yet — waiting for first check cycle.</p>" if not bots else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <title>Chat Monitor Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           background: #f1f5f9; color: #1e293b; min-height: 100vh; }}

    header {{ background: #0f172a; color: #f8fafc; padding: 1.25rem 2rem;
              display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem; }}
    header h1 {{ font-size: 1.25rem; font-weight: 600; letter-spacing: -0.02em; }}
    .overall {{ font-size: 1.75rem; font-weight: 700; color: {overall_color}; }}
    .header-meta {{ font-size: 0.8rem; color: #94a3b8; text-align: right; line-height: 1.6; }}

    .summary {{ display: flex; gap: 1rem; padding: 1rem 2rem; flex-wrap: wrap; }}
    .summary-pill {{ padding: 0.4rem 1rem; border-radius: 999px; font-size: 0.85rem; font-weight: 600; }}

    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
             gap: 1rem; padding: 0 2rem 2rem; }}

    .card {{ background: #fff; border-radius: 0.5rem; padding: 1rem;
             box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
    .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }}
    .bot-name {{ font-weight: 600; font-size: 1rem; }}
    .badge {{ font-size: 0.7rem; font-weight: 700; padding: 0.2rem 0.6rem;
              border-radius: 999px; letter-spacing: 0.04em; }}
    .card-meta {{ font-size: 0.8rem; color: #475569; display: flex; gap: 1rem; margin-bottom: 0.4rem; }}
    .response-text {{ font-size: 0.78rem; color: #64748b; font-style: italic;
                      margin-top: 0.4rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .error-text {{ font-size: 0.75rem; color: #dc2626; margin-top: 0.35rem; }}
    .card-ts {{ font-size: 0.7rem; color: #94a3b8; margin-top: 0.5rem; }}

    footer {{ text-align: center; padding: 1.5rem; font-size: 0.75rem; color: #94a3b8; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Chat Monitor</h1>
      <div class="overall">{up}/{total} UP</div>
    </div>
    <div class="header-meta">
      Last cycle: {last_cycle}<br>
      Page refreshes every 60s
    </div>
  </header>

  <div class="summary">
    <span class="summary-pill" style="background:#dcfce7;color:#16a34a;">{up} UP</span>
    {"<span class='summary-pill' style='background:#fef3c7;color:#d97706;'>" + str(degraded) + " DEGRADED</span>" if degraded else ""}
    {"<span class='summary-pill' style='background:#fee2e2;color:#dc2626;'>" + str(down) + " DOWN</span>" if down else ""}
  </div>

  <div class="grid">
    {cards_html}
  </div>
  {no_data}

  <footer>Generated at {now} · <a href="/" style="color:#94a3b8;">Refresh</a></footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        bots, cycle = parse_log()
        html = build_html(bots, cycle)
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # suppress request noise


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), Handler)
    print(f"Dashboard running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
