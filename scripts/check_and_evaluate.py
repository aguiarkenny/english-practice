"""
Check Gmail inbox for a reply to the latest practice email, evaluate it, and send feedback.

Usage:
    python scripts/check_and_evaluate.py

Required environment variables:
    ANTHROPIC_API_KEY
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, RECIPIENT_EMAIL
"""

import email
import imaplib
import os
import re
import sys
from email.header import decode_header

import anthropic

sys.path.insert(0, os.path.dirname(__file__))
from utils import load_state, save_state, send_email, update_scores_and_level

RUBRIC = """
GRAMMAR/SPELLING (1–5):
1 = Errors that prevent comprehension
2 = Frequent errors, still comprehensible
3 = Occasional errors, does not impede understanding
4 = Minimal errors
5 = No notable errors

SEMANTICS (1–5):
1 = Response is off-topic or irrelevant to the text
2 = Partially relevant, misses key points
3 = Relevant but superficial analysis
4 = Good technical understanding, well-articulated
5 = Precise insight, directly addresses the task with depth

FLUENCY (1–5):
1 = Clearly a literal translation from Portuguese
2 = Portuguese sentence structure is apparent
3 = Functional but unnatural in places
4 = Sounds natural for most of the text
5 = Reads like a professional native English writer
"""

EVALUATION_PROMPT = """You are an expert English language evaluator for non-native professionals.
Your student is a Brazilian data scientist with advanced technical knowledge but basic English writing skills.

CONTEXT:
Topic: {topic} › {subtopic}
Date: {date}

ARTICLE THE STUDENT READ:
{article}

WRITING TASK GIVEN TO STUDENT:
{writing_task}

STUDENT'S RESPONSE:
{student_response}

EVALUATION RUBRIC:
{rubric}

INSTRUCTIONS:
Evaluate the student's response strictly and consistently using the rubric above.
Do not give inflated scores — a score of 4 or 5 should be genuinely earned.

Provide your evaluation in EXACTLY this format:

---SCORES---
grammar: [1-5]
semantics: [1-5]
fluency: [1-5]

---GRAMMAR FEEDBACK---
[List specific errors found with corrections. If none, say "No notable errors." Be specific: quote the error, show the correction, explain the rule briefly.]

---SEMANTICS FEEDBACK---
[Assess whether the response addresses the task correctly and shows understanding of the technical content. Quote relevant parts.]

---FLUENCY FEEDBACK---
[Identify phrases that sound translated or unnatural. Suggest more natural alternatives. Quote specific phrases.]

---SUGGESTED REWRITE---
[Write an improved version of the student's response at their current level (writing level {writing_level}/5), correcting all issues while preserving their ideas.]

---RECURRING ERRORS---
[List 0–3 error PATTERNS (not just single occurrences) that should be tracked for future sessions. Format: one pattern per line, concise description. If no new patterns, write NONE.]
---END---
"""


def decode_str(value: str) -> str:
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def get_text_body(msg) -> str:
    """Extract plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if ctype == "text/plain" and "attachment" not in disp:
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        charset = msg.get_content_charset() or "utf-8"
        return msg.get_payload(decode=True).decode(charset, errors="replace")
    return ""


def strip_quoted_reply(text: str) -> str:
    """Remove quoted original email from reply body."""
    lines = text.splitlines()
    clean = []
    for line in lines:
        # Common reply separators
        if re.match(r"^(>|On .+ wrote:|_{10,}|-{10,}|From:)", line.strip()):
            break
        clean.append(line)
    return "\n".join(clean).strip()


def find_reply_in_inbox(session_num: int, subtopic: str) -> str | None:
    """Search Gmail inbox for a reply to the practice email. Returns body text or None."""
    imap_host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]

    # Build expected subject patterns
    base_subject = f"[English Practice] Session #{session_num}"
    reply_subject = f"Re: {base_subject}"

    mail = imaplib.IMAP4_SSL(imap_host)
    mail.login(smtp_user, smtp_password)
    mail.select("inbox")

    # Search only UNSEEN replies to avoid reprocessing already-evaluated responses
    search_term = f'UNSEEN SUBJECT "{reply_subject}"'
    status, data = mail.search(None, search_term)

    if status != "OK" or not data[0]:
        mail.logout()
        return None

    # Get the most recent matching message
    msg_ids = data[0].split()
    latest_id = msg_ids[-1]

    status, msg_data = mail.fetch(latest_id, "(RFC822)")

    if status != "OK":
        mail.logout()
        return None

    # Mark as read so it is never processed again
    mail.store(latest_id, "+FLAGS", "\\Seen")
    mail.logout()

    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)
    body = get_text_body(msg)
    return strip_quoted_reply(body)


def parse_evaluation(raw: str) -> dict:
    sections = {}
    markers = [
        "---SCORES---",
        "---GRAMMAR FEEDBACK---",
        "---SEMANTICS FEEDBACK---",
        "---FLUENCY FEEDBACK---",
        "---SUGGESTED REWRITE---",
        "---RECURRING ERRORS---",
        "---END---",
    ]
    current = None
    lines = []

    for line in raw.splitlines():
        if line.strip() in markers:
            if current:
                sections[current] = "\n".join(lines).strip()
            current = line.strip()
            lines = []
        else:
            if current:
                lines.append(line)

    scores = {}
    for line in sections.get("---SCORES---", "").splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            try:
                scores[key.strip()] = int(val.strip())
            except ValueError:
                pass

    new_errors = []
    for line in sections.get("---RECURRING ERRORS---", "").splitlines():
        line = line.strip()
        if line and line.upper() != "NONE" and not line.startswith("---"):
            new_errors.append(line.lstrip("-• ").strip())

    return {
        "scores": scores,
        "grammar_feedback": sections.get("---GRAMMAR FEEDBACK---", ""),
        "semantics_feedback": sections.get("---SEMANTICS FEEDBACK---", ""),
        "fluency_feedback": sections.get("---FLUENCY FEEDBACK---", ""),
        "suggested_rewrite": sections.get("---SUGGESTED REWRITE---", ""),
        "new_errors": new_errors,
    }


def build_feedback_email(ev: dict, pending: dict, state: dict, old_level: int) -> tuple[str, str]:
    scores = ev["scores"]
    avg = sum(scores.values()) / len(scores) if scores else 0
    session_num = pending["session_num"]
    subtopic = pending["subtopic"].title()
    new_level = state.get("writing_level", 1)

    level_change = ""
    if new_level > old_level:
        level_change = f'<p style="color:#2e7d32;font-weight:bold;">★ Writing level UP: {old_level} → {new_level}</p>'
    elif new_level < old_level:
        level_change = f'<p style="color:#c62828;font-weight:bold;">↓ Writing level DOWN: {old_level} → {new_level} — keep practicing!</p>'

    def section(title, body):
        body_html = "".join(f"<p>{p.strip()}</p>" for p in body.split("\n\n") if p.strip()) or f"<p>{body}</p>"
        return f'<h2 style="color:#2980b9;border-bottom:1px solid #ddd;padding-bottom:4px;">{title}</h2>{body_html}'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body{{font-family:Georgia,serif;max-width:680px;margin:0 auto;padding:24px;color:#1a1a1a;line-height:1.7}}
  .score-box{{background:#f8f9fa;border-left:4px solid #3498db;padding:12px 20px;margin:16px 0}}
  .score-row{{display:flex;gap:24px;flex-wrap:wrap}}
  .score-item{{text-align:center;min-width:80px}}
  .score-num{{font-size:2em;font-weight:bold;color:#2c3e50}}
  .score-label{{font-size:0.8em;color:#666}}
  .avg{{font-size:1.1em;color:#2980b9;font-weight:bold;margin-top:8px}}
  .rewrite{{background:#e8f5e9;border:1px solid #a5d6a7;border-radius:6px;padding:16px 20px;margin:16px 0}}
  h2{{font-size:1.1em}}
</style>
</head><body>
<h1 style="font-size:1.4em;color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:8px;">
  Feedback — Session #{session_num} · {subtopic}
</h1>

<div class="score-box">
  <div class="score-row">
    <div class="score-item"><div class="score-num">{scores.get("grammar","?")}</div><div class="score-label">Grammar</div></div>
    <div class="score-item"><div class="score-num">{scores.get("semantics","?")}</div><div class="score-label">Semantics</div></div>
    <div class="score-item"><div class="score-num">{scores.get("fluency","?")}</div><div class="score-label">Fluency</div></div>
  </div>
  <div class="avg">Average: {avg:.1f} / 5</div>
  {level_change}
</div>

{section("Grammar Feedback", ev["grammar_feedback"])}
{section("Semantics Feedback", ev["semantics_feedback"])}
{section("Fluency Feedback", ev["fluency_feedback"])}

<h2 style="color:#2980b9;border-bottom:1px solid #ddd;padding-bottom:4px;">Suggested Rewrite</h2>
<div class="rewrite">{ev["suggested_rewrite"]}</div>

<p style="font-size:0.8em;color:#888;border-top:1px solid #eee;padding-top:12px;margin-top:40px;">
  English Practice Agent · Auto-generated feedback
</p>
</body></html>"""

    text = f"""FEEDBACK — Session #{session_num} · {subtopic}

SCORES:
  Grammar:   {scores.get("grammar","?")} / 5
  Semantics: {scores.get("semantics","?")} / 5
  Fluency:   {scores.get("fluency","?")} / 5
  Average:   {avg:.1f} / 5

GRAMMAR FEEDBACK
{ev["grammar_feedback"]}

SEMANTICS FEEDBACK
{ev["semantics_feedback"]}

FLUENCY FEEDBACK
{ev["fluency_feedback"]}

SUGGESTED REWRITE
{ev["suggested_rewrite"]}
"""
    return html, text


def main():
    state = load_state()
    pending = state.get("pending_evaluation")

    if not pending:
        print("No pending evaluation in state. Nothing to do.")
        sys.exit(0)

    session_num = pending["session_num"]
    subtopic = pending["subtopic"]
    print(f"Checking inbox for reply to Session #{session_num} ({subtopic})...")

    student_response = find_reply_in_inbox(session_num, subtopic)

    if not student_response:
        print("No reply found yet.")
        sys.exit(0)

    print(f"Reply found ({len(student_response)} chars). Evaluating...")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": EVALUATION_PROMPT.format(
                    topic=pending["topic"],
                    subtopic=subtopic,
                    date=pending["date"],
                    article=pending["article"],
                    writing_task=pending["writing_task"],
                    student_response=student_response,
                    rubric=RUBRIC,
                    writing_level=state["writing_level"],
                ),
            }
        ],
    )

    ev = parse_evaluation(message.content[0].text)
    old_level = state["writing_level"]
    state = update_scores_and_level(state, ev["scores"])

    existing_errors = state.get("recurring_errors", [])
    for err in ev["new_errors"]:
        if err not in existing_errors:
            existing_errors.append(err)
    state["recurring_errors"] = existing_errors[-10:]
    state["pending_evaluation"] = None
    save_state(state)

    html, text = build_feedback_email(ev, pending, state, old_level)
    subject = f"[English Practice] Feedback — Session #{session_num} · {subtopic.title()}"
    send_email(subject, html, text)
    print(f"Feedback sent: {subject}")


if __name__ == "__main__":
    main()
