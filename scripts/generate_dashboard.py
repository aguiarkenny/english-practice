"""
Generate a static HTML dashboard from state.json and write it to docs/index.html.
GitHub Pages serves the docs/ folder.

Usage:
    python scripts/generate_dashboard.py
"""

import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(__file__))
from utils import load_state

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")

LEVEL_LABELS = {
    1: "Beginner",
    2: "Elementary",
    3: "Intermediate",
    4: "Upper-intermediate",
    5: "Advanced",
}

READING_LEVEL_LABELS = {
    1: "B2",
    2: "C1",
    3: "C1+",
    4: "C2",
    5: "C2 native",
}


def build_dashboard(state: dict) -> str:
    writing_level = state.get("writing_level", 1)
    reading_level = state.get("reading_level", 1)
    session_count = state.get("session_count", 0)
    last_session = state.get("last_session_date") or "—"
    all_scores = state.get("recent_writing_scores", [])
    errors = state.get("recurring_errors", [])
    topics = state.get("topic_history", [])

    # Chart data
    chart_labels = json.dumps([s["date"] for s in all_scores])
    chart_grammar = json.dumps([s["scores"].get("grammar", 0) for s in all_scores])
    chart_semantics = json.dumps([s["scores"].get("semantics", 0) for s in all_scores])
    chart_fluency = json.dumps([s["scores"].get("fluency", 0) for s in all_scores])
    chart_avg = json.dumps([s["avg"] for s in all_scores])

    # Score history table rows
    table_rows = ""
    for s in reversed(all_scores):
        avg = s["avg"]
        color = "#2e7d32" if avg >= 4.0 else "#c62828" if avg < 3.0 else "#1565c0"
        d = s["date"]
        g = s["scores"].get("grammar", "–")
        sem = s["scores"].get("semantics", "–")
        fl = s["scores"].get("fluency", "–")
        table_rows += (
            f'<tr><td>{d}</td><td>{g}</td><td>{sem}</td><td>{fl}</td>'
            f'<td style="color:{color};font-weight:bold">{avg:.1f}</td></tr>'
        )

    errors_html = "".join(f"<li>{e}</li>" for e in errors) or "<li>None identified yet — keep writing!</li>"

    topics_html = "".join(
        f"<tr><td>{t['date']}</td><td>{t['topic'].title()}</td><td>{t['subtopic'].title()}</td></tr>"
        for t in reversed(topics[-20:])
    ) or "<tr><td colspan='3'>No sessions yet.</td></tr>"

    # Writing level progress bar toward next level
    if all_scores:
        recent5 = [s["avg"] for s in all_scores[-5:]]
        progress_toward_next = min(100, int(sum(recent5) / len(recent5) / 4.0 * 100))
        avg_last5_str = f"{sum(s['avg'] for s in all_scores[-5:]) / len(all_scores[-5:]):.1f}"
    else:
        progress_toward_next = 0
        avg_last5_str = "—"

    score_history_html = (
        "<p style=\"color:#888;font-size:.9em\">No evaluated sessions yet.</p>"
        if not all_scores
        else f"<table><tr><th>Date</th><th>Grammar</th><th>Semantics</th><th>Fluency</th><th>Average</th></tr>{table_rows}</table>"
    )

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    no_chart = len(all_scores) == 0
    chart_section = "" if no_chart else (
        '<div class="card full"><h2>Score Trend</h2>'
        '<canvas id="scoreChart" height="80"></canvas></div>'
    )

    chart_script = "" if no_chart else f"""
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
    <script>
    const ctx = document.getElementById('scoreChart').getContext('2d');
    new Chart(ctx, {{
      type: 'line',
      data: {{
        labels: {chart_labels},
        datasets: [
          {{ label: 'Grammar', data: {chart_grammar}, borderColor: '#e53935', tension: 0.3, fill: false }},
          {{ label: 'Semantics', data: {chart_semantics}, borderColor: '#1e88e5', tension: 0.3, fill: false }},
          {{ label: 'Fluency', data: {chart_fluency}, borderColor: '#43a047', tension: 0.3, fill: false }},
          {{ label: 'Average', data: {chart_avg}, borderColor: '#6d4c41', borderWidth: 2, borderDash: [5,3], tension: 0.3, fill: false }},
        ]
      }},
      options: {{
        scales: {{
          y: {{ min: 0, max: 5, ticks: {{ stepSize: 1 }} }}
        }},
        plugins: {{ legend: {{ position: 'bottom' }} }}
      }}
    }});
    </script>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>English Practice — Dashboard</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f4f8;color:#1a1a1a;padding:24px}}
    h1{{font-size:1.5em;color:#2c3e50;margin-bottom:4px}}
    .subtitle{{color:#888;font-size:0.85em;margin-bottom:24px}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px;margin-bottom:24px}}
    .card{{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
    .card.full{{grid-column:1/-1}}
    .card h2{{font-size:0.85em;color:#888;text-transform:uppercase;letter-spacing:.05em;margin-bottom:12px}}
    .big-num{{font-size:2.8em;font-weight:700;color:#2c3e50;line-height:1}}
    .big-label{{font-size:0.75em;color:#666;margin-top:4px}}
    .level-bar-track{{background:#e0e0e0;border-radius:4px;height:8px;margin-top:10px}}
    .level-bar-fill{{height:8px;border-radius:4px;background:#3498db;transition:width .5s}}
    .level-hint{{font-size:0.7em;color:#888;margin-top:4px}}
    table{{border-collapse:collapse;width:100%;font-size:0.85em}}
    th{{background:#e3f2fd;padding:8px 10px;text-align:left;border:1px solid #ddd;font-weight:600}}
    td{{padding:7px 10px;border:1px solid #ddd}}
    tr:nth-child(even){{background:#f9f9f9}}
    ul{{padding-left:18px;font-size:0.9em;line-height:2}}
    .footer{{margin-top:32px;font-size:0.75em;color:#aaa;text-align:center}}
  </style>
</head>
<body>
  <h1>English Practice — Progress Dashboard</h1>
  <p class="subtitle">Last updated: {generated_at} · Last session: {last_session}</p>

  <div class="grid">
    <div class="card">
      <h2>Writing Level</h2>
      <div class="big-num">{writing_level}<span style="font-size:.4em;color:#999">/5</span></div>
      <div class="big-label">{LEVEL_LABELS.get(writing_level,'')}</div>
      <div class="level-bar-track"><div class="level-bar-fill" style="width:{writing_level/5*100:.0f}%"></div></div>
      <div class="level-hint">Progress toward next level: {progress_toward_next}% (based on last 5 sessions avg)</div>
    </div>

    <div class="card">
      <h2>Reading Level</h2>
      <div class="big-num">{reading_level}<span style="font-size:.4em;color:#999">/5</span></div>
      <div class="big-label">{READING_LEVEL_LABELS.get(reading_level,'')}</div>
      <div class="level-bar-track"><div class="level-bar-fill" style="width:{reading_level/5*100:.0f}%"></div></div>
    </div>

    <div class="card">
      <h2>Sessions Completed</h2>
      <div class="big-num">{session_count}</div>
      <div class="big-label">total practice sessions</div>
    </div>

    <div class="card">
      <h2>Avg Score (last 5)</h2>
      <div class="big-num">
        {avg_last5_str}
        <span style="font-size:.4em;color:#999">/5</span>
      </div>
      <div class="big-label">grammar · semantics · fluency</div>
    </div>

    {chart_section}

    <div class="card full">
      <h2>Score History</h2>
      {score_history_html}
    </div>

    <div class="card">
      <h2>Recurring Errors to Watch</h2>
      <ul>{errors_html}</ul>
    </div>

    <div class="card full">
      <h2>Topics Covered (last 20)</h2>
      <table>
        <tr><th>Date</th><th>Area</th><th>Subtopic</th></tr>
        {topics_html}
      </table>
    </div>
  </div>

  <div class="footer">English Practice Agent · Auto-generated · Private</div>
  {chart_script}
</body>
</html>"""


def main():
    state = load_state()
    os.makedirs(DOCS_DIR, exist_ok=True)
    output_path = os.path.join(DOCS_DIR, "index.html")
    html = build_dashboard(state)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard written to {output_path}")


if __name__ == "__main__":
    main()
