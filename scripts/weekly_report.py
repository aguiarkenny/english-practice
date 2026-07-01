"""
Generate and send a weekly progress report email.

Usage:
    python scripts/weekly_report.py

Required environment variables:
    ANTHROPIC_API_KEY
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, RECIPIENT_EMAIL
"""

import os
import sys
from datetime import date, datetime, timedelta

import anthropic

sys.path.insert(0, os.path.dirname(__file__))
from utils import load_state, send_email

LEVEL_LABELS = {
    1: "Beginner — guided sentences",
    2: "Elementary — short paragraphs",
    3: "Intermediate — argued paragraphs",
    4: "Upper-intermediate — professional emails",
    5: "Advanced — executive documents",
}

READING_LEVEL_LABELS = {
    1: "B2 upper-intermediate",
    2: "C1 advanced",
    3: "C1+ dense technical",
    4: "C2 near-native",
    5: "C2 native academic",
}


def bar(value: float, max_value: float = 5.0, width: int = 20) -> str:
    filled = int(round(value / max_value * width))
    return "█" * filled + "░" * (width - filled)


def sessions_this_week(state: dict) -> list[dict]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    week_scores = []
    for s in state.get("recent_writing_scores", []):
        d = datetime.strptime(s["date"], "%Y-%m-%d").date()
        if d >= monday:
            week_scores.append(s)
    return week_scores


def build_insight_prompt(state: dict, week_scores: list[dict]) -> str:
    errors = state.get("recurring_errors", [])
    scores_summary = "\n".join(
        f"- Session on {s['date']}: grammar={s['scores'].get('grammar','?')} "
        f"semantics={s['scores'].get('semantics','?')} fluency={s['scores'].get('fluency','?')} avg={s['avg']}"
        for s in week_scores
    ) or "No sessions this week."

    errors_summary = "\n".join(f"- {e}" for e in errors) or "None identified yet."

    return f"""You are an English learning coach reviewing a student's weekly progress.
The student is a Brazilian data scientist working on technical English writing.

CURRENT STATE:
- Writing level: {state.get('writing_level', 1)}/5
- Reading level: {state.get('reading_level', 1)}/5
- Total sessions completed: {state.get('session_count', 0)}

THIS WEEK'S SESSIONS:
{scores_summary}

RECURRING ERRORS TRACKED:
{errors_summary}

Write a short, encouraging weekly coaching note (3–5 sentences) that:
1. Acknowledges this week's performance specifically (reference the scores)
2. Highlights the most important area to focus on next week
3. Gives one concrete, actionable tip related to the recurring errors

Be direct and specific. Avoid generic praise. Tone: professional coach, not cheerleader.
Output only the coaching note, no headers or labels."""


def build_report_html(state: dict, week_scores: list[dict], insight: str) -> tuple[str, str]:
    today = date.today()
    writing_level = state.get("writing_level", 1)
    reading_level = state.get("reading_level", 1)
    session_count = state.get("session_count", 0)
    errors = state.get("recurring_errors", [])

    # Week scores summary
    if week_scores:
        avg_grammar = sum(s["scores"].get("grammar", 0) for s in week_scores) / len(week_scores)
        avg_semantics = sum(s["scores"].get("semantics", 0) for s in week_scores) / len(week_scores)
        avg_fluency = sum(s["scores"].get("fluency", 0) for s in week_scores) / len(week_scores)
        avg_total = sum(s["avg"] for s in week_scores) / len(week_scores)
        n_sessions = len(week_scores)
    else:
        avg_grammar = avg_semantics = avg_fluency = avg_total = 0.0
        n_sessions = 0

    # All-time score trend (last 10)
    all_scores = state.get("recent_writing_scores", [])[-10:]
    trend_rows = ""
    for s in all_scores:
        avg = s["avg"]
        color = "#2e7d32" if avg >= 4.0 else "#e65100" if avg < 3.0 else "#1565c0"
        trend_rows += f"""
        <tr>
          <td>{s['date']}</td>
          <td>{s['scores'].get('grammar','–')}</td>
          <td>{s['scores'].get('semantics','–')}</td>
          <td>{s['scores'].get('fluency','–')}</td>
          <td style="color:{color};font-weight:bold">{avg:.1f}</td>
        </tr>"""

    errors_html = "".join(f"<li>{e}</li>" for e in errors) if errors else "<li>None identified yet.</li>"

    # Topic history (last 5)
    topics = state.get("topic_history", [])[-5:]
    topics_html = "".join(
        f"<li>{t['date']} — <strong>{t['topic'].title()}</strong>: {t['subtopic'].title()}</li>"
        for t in reversed(topics)
    ) or "<li>No sessions yet.</li>"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body{{font-family:Georgia,serif;max-width:700px;margin:0 auto;padding:24px;color:#1a1a1a;line-height:1.7}}
  h1{{font-size:1.4em;color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:8px}}
  h2{{font-size:1.05em;color:#2980b9;margin-top:28px;border-bottom:1px solid #eee;padding-bottom:4px}}
  .meta{{background:#f8f9fa;border-left:4px solid #3498db;padding:12px 16px;margin-bottom:20px;font-size:0.9em}}
  .grid{{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0}}
  .card{{flex:1;min-width:140px;background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px;text-align:center}}
  .card-num{{font-size:2em;font-weight:bold;color:#2c3e50}}
  .card-label{{font-size:0.75em;color:#666;margin-top:2px}}
  .score-bar{{display:flex;align-items:center;gap:10px;margin:6px 0;font-size:0.9em}}
  .bar-track{{flex:1;background:#eee;border-radius:4px;height:10px}}
  .bar-fill{{height:10px;border-radius:4px;background:#3498db}}
  .insight{{background:#e8f5e9;border:1px solid #a5d6a7;border-radius:6px;padding:14px 18px;margin:16px 0;font-style:italic}}
  table{{border-collapse:collapse;width:100%;font-size:0.88em}}
  th{{background:#e3f2fd;padding:7px 10px;text-align:left;border:1px solid #ddd}}
  td{{padding:7px 10px;border:1px solid #ddd}}
  tr:nth-child(even){{background:#f9f9f9}}
  ul{{margin:8px 0;padding-left:20px}}
  .footer{{margin-top:40px;font-size:0.8em;color:#888;border-top:1px solid #eee;padding-top:12px}}
</style>
</head><body>
<h1>Weekly Progress Report</h1>
<div class="meta">
  <strong>Week ending:</strong> {today.strftime("%B %d, %Y")} &nbsp;|&nbsp;
  <strong>Total sessions:</strong> {session_count}
</div>

<div class="grid">
  <div class="card">
    <div class="card-num">{writing_level}<span style="font-size:0.5em;color:#999">/5</span></div>
    <div class="card-label">Writing Level</div>
    <div style="font-size:0.7em;color:#555;margin-top:4px">{LEVEL_LABELS.get(writing_level,'')}</div>
  </div>
  <div class="card">
    <div class="card-num">{reading_level}<span style="font-size:0.5em;color:#999">/5</span></div>
    <div class="card-label">Reading Level</div>
    <div style="font-size:0.7em;color:#555;margin-top:4px">{READING_LEVEL_LABELS.get(reading_level,'')}</div>
  </div>
  <div class="card">
    <div class="card-num">{n_sessions}</div>
    <div class="card-label">Sessions This Week</div>
  </div>
  <div class="card">
    <div class="card-num">{avg_total:.1f}<span style="font-size:0.5em;color:#999">/5</span></div>
    <div class="card-label">Avg Score This Week</div>
  </div>
</div>

<h2>This Week's Scores</h2>
{"<p style='color:#888'>No evaluated sessions this week.</p>" if n_sessions == 0 else f"""
<div class="score-bar"><span style="width:80px">Grammar</span><div class="bar-track"><div class="bar-fill" style="width:{avg_grammar/5*100:.0f}%"></div></div><span>{avg_grammar:.1f}</span></div>
<div class="score-bar"><span style="width:80px">Semantics</span><div class="bar-track"><div class="bar-fill" style="width:{avg_semantics/5*100:.0f}%"></div></div><span>{avg_semantics:.1f}</span></div>
<div class="score-bar"><span style="width:80px">Fluency</span><div class="bar-track"><div class="bar-fill" style="width:{avg_fluency/5*100:.0f}%"></div></div><span>{avg_fluency:.1f}</span></div>
"""}

<h2>Coach's Note</h2>
<div class="insight">{insight}</div>

<h2>Score History (last 10 sessions)</h2>
{"<p style='color:#888'>No sessions yet.</p>" if not all_scores else f"""
<table>
  <tr><th>Date</th><th>Grammar</th><th>Semantics</th><th>Fluency</th><th>Avg</th></tr>
  {trend_rows}
</table>"""}

<h2>Recurring Errors to Watch</h2>
<ul>{errors_html}</ul>

<h2>Recent Topics Covered</h2>
<ul>{topics_html}</ul>

<div class="footer">English Practice Agent · Weekly Report · Auto-generated</div>
</body></html>"""

    text = f"""WEEKLY PROGRESS REPORT — {today.strftime("%B %d, %Y")}

Writing Level: {writing_level}/5 — {LEVEL_LABELS.get(writing_level,'')}
Reading Level: {reading_level}/5 — {READING_LEVEL_LABELS.get(reading_level,'')}
Sessions this week: {n_sessions} | Avg score: {avg_total:.1f}/5
Total sessions completed: {session_count}

THIS WEEK'S SCORES:
  Grammar:   {avg_grammar:.1f}/5
  Semantics: {avg_semantics:.1f}/5
  Fluency:   {avg_fluency:.1f}/5

COACH'S NOTE:
{insight}

RECURRING ERRORS:
{chr(10).join(f'- {e}' for e in errors) or '- None yet.'}
"""
    return html, text


def main():
    state = load_state()
    week_scores = sessions_this_week(state)

    print("Generating weekly insight...")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": build_insight_prompt(state, week_scores)}],
    )
    insight = message.content[0].text.strip()

    html, text = build_report_html(state, week_scores, insight)

    today = date.today()
    subject = f"[English Practice] Weekly Report — {today.strftime('%b %d')}"
    print(f"Sending: {subject}")
    send_email(subject, html, text)
    print("Done.")


if __name__ == "__main__":
    main()
