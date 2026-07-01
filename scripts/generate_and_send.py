"""
Daily English practice generator and sender.

Usage:
    python scripts/generate_and_send.py

Required environment variables:
    ANTHROPIC_API_KEY
    SMTP_HOST          e.g. smtp.gmail.com
    SMTP_PORT          e.g. 587
    SMTP_USER          your Gmail address
    SMTP_PASSWORD      Gmail App Password
    RECIPIENT_EMAIL    where to send (usually same as SMTP_USER)
"""

import os
import sys
from datetime import date

import anthropic

sys.path.insert(0, os.path.dirname(__file__))
from utils import (
    get_writing_task_prompt,
    load_state,
    pick_topic,
    save_state,
    send_email,
    should_include_error_review,
)

READING_LEVEL_DESCRIPTORS = {
    1: "B2 upper-intermediate",
    2: "C1 advanced",
    3: "C1+ advanced with dense technical content",
    4: "C2 near-native technical writing",
    5: "C2 native-level technical and academic prose",
}


def build_generation_prompt(
    topic: str,
    subtopic: str,
    reading_level: int,
    writing_level: int,
    writing_task: str,
    error_review: list[str],
    include_error_review: bool,
) -> str:
    level_desc = READING_LEVEL_DESCRIPTORS.get(reading_level, "C1 advanced")

    error_section = ""
    if include_error_review and error_review:
        errors_fmt = "\n".join(f"- {e}" for e in error_review[-5:])
        error_section = f"""
RECURRING ERRORS TO REINFORCE:
The learner has repeatedly made these mistakes in previous sessions. Weave one or two
subtle exercises or references into the reading text that help reinforce awareness of these
patterns (don't be heavy-handed — it should feel natural):
{errors_fmt}
"""

    return f"""You are an English language coach specializing in technical business writing.
Your student is a Brazilian data scientist with advanced technical reading comprehension
but basic writing skills. They work with data science, revenue operations, and sales compensation.

TODAY'S TASK: Generate a complete daily English practice session.

TOPIC AREA: {topic}
SPECIFIC SUBTOPIC: {subtopic}
READING LEVEL TARGET: {level_desc}
WRITING LEVEL: {writing_level} out of 5 (1=short guided sentences, 5=formal executive documents)
{error_section}

INSTRUCTIONS:

1. READING TEXT (300–500 words):
   - Write an original, substantive article on the subtopic above.
   - Use vocabulary and sentence complexity appropriate for {level_desc} English.
   - Keep individual sentences readable aloud — avoid excessively long, nested clauses.
   - Ground the content in real-world practice (not just theory).
   - Use concrete examples, data references, or case-like scenarios.
   - Write in a professional but engaging register (think: Harvard Business Review meets technical blog).

2. WRITING TASK:
   - After the article, present this specific writing demand to the student:
     "{writing_task}"
   - Tailor the task so it directly relates to content in the article above.
   - Be specific about what the student should address.

3. VOCABULARY SPOTLIGHT:
   - After the writing task, list 5 key technical terms or phrases from the article.
   - For each: term | brief definition (1 sentence) | example sentence from the article.

FORMAT YOUR RESPONSE EXACTLY AS:

---ARTICLE---
[article text here]

---WRITING TASK---
[specific writing task here]

---VOCABULARY SPOTLIGHT---
[5 terms in the format specified]
---END---
"""


def parse_response(raw: str) -> dict:
    sections = {}
    markers = ["---ARTICLE---", "---WRITING TASK---", "---VOCABULARY SPOTLIGHT---", "---END---"]
    current = None
    lines = []

    for line in raw.splitlines():
        stripped = line.strip()
        if stripped in markers:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = stripped
            lines = []
        else:
            if current is not None:
                lines.append(line)

    return {
        "article": sections.get("---ARTICLE---", ""),
        "writing_task": sections.get("---WRITING TASK---", ""),
        "vocabulary": sections.get("---VOCABULARY SPOTLIGHT---", ""),
    }


def build_email_html(
    session_num: int,
    topic: str,
    subtopic: str,
    article: str,
    writing_task: str,
    vocabulary: str,
    writing_level: int,
    reading_level: int,
) -> tuple[str, str]:
    today = date.today().strftime("%B %d, %Y")
    article_html = "".join(
        f"<p>{p.strip()}</p>" for p in article.split("\n\n") if p.strip()
    )
    vocab_rows = ""
    for line in vocabulary.splitlines():
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                term = parts[0]
                rest = " | ".join(parts[1:])
                vocab_rows += f"<tr><td><strong>{term}</strong></td><td>{rest}</td></tr>"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Georgia, serif; max-width: 680px; margin: 0 auto; padding: 24px; color: #1a1a1a; line-height: 1.7; }}
  h1 {{ font-size: 1.4em; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px; }}
  h2 {{ font-size: 1.1em; color: #2980b9; margin-top: 32px; }}
  .meta {{ background: #f8f9fa; border-left: 4px solid #3498db; padding: 12px 16px; margin-bottom: 24px; font-size: 0.9em; }}
  .article {{ background: #fff; }}
  .task-box {{ background: #fff8e1; border: 1px solid #f9a825; border-radius: 6px; padding: 16px 20px; margin: 24px 0; }}
  .task-box strong {{ color: #e65100; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
  td {{ border: 1px solid #ddd; padding: 8px 12px; vertical-align: top; font-size: 0.9em; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  .footer {{ margin-top: 40px; font-size: 0.8em; color: #888; border-top: 1px solid #eee; padding-top: 12px; }}
  .level-badge {{ display: inline-block; background: #e8f5e9; color: #2e7d32; border-radius: 12px; padding: 2px 10px; font-size: 0.8em; font-weight: bold; }}
</style>
</head>
<body>
<h1>Daily English Practice — Session #{session_num}</h1>
<div class="meta">
  <strong>Date:</strong> {today}<br>
  <strong>Topic:</strong> {topic.title()} › {subtopic.title()}<br>
  <strong>Reading level:</strong> <span class="level-badge">L{reading_level}/5</span>
  &nbsp;<strong>Writing level:</strong> <span class="level-badge">L{writing_level}/5</span>
</div>

<h2>Reading</h2>
<div class="article">
{article_html}
</div>

<div class="task-box">
  <strong>✍️ Your writing task:</strong><br><br>
  {writing_task}
  <br><br>
  <em>When done, run: <code>python scripts/submit_response.py</code> and paste your answer.</em>
</div>

<h2>Vocabulary Spotlight</h2>
<table>
  <tr style="background:#e3f2fd;"><td><strong>Term</strong></td><td><strong>Definition & Example</strong></td></tr>
  {vocab_rows}
</table>

<div class="footer">
  English Practice Agent · Auto-generated · Reply to this email is not monitored.
</div>
</body>
</html>"""

    text = f"""DAILY ENGLISH PRACTICE — Session #{session_num}
{today} | {topic.title()} › {subtopic.title()}
Reading L{reading_level}/5 | Writing L{writing_level}/5

=== READING ===

{article}

=== WRITING TASK ===

{writing_task}

When done, run: python scripts/submit_response.py

=== VOCABULARY SPOTLIGHT ===

{vocabulary}
"""
    return html, text


def main():
    state = load_state()

    topic, subtopic = pick_topic(state)
    writing_task = get_writing_task_prompt(state["writing_level"])
    include_errors = should_include_error_review(state)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print(f"Generating content: {topic} › {subtopic} ...")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": build_generation_prompt(
                    topic=topic,
                    subtopic=subtopic,
                    reading_level=state["reading_level"],
                    writing_level=state["writing_level"],
                    writing_task=writing_task,
                    error_review=state.get("recurring_errors", []),
                    include_error_review=include_errors,
                ),
            }
        ],
    )

    raw = message.content[0].text
    parsed = parse_response(raw)

    session_num = state["session_count"] + 1
    html, text = build_email_html(
        session_num=session_num,
        topic=topic,
        subtopic=subtopic,
        article=parsed["article"],
        writing_task=parsed["writing_task"],
        vocabulary=parsed["vocabulary"],
        writing_level=state["writing_level"],
        reading_level=state["reading_level"],
    )

    subject = f"[English Practice] Session #{session_num} — {subtopic.title()}"
    print(f"Sending email: {subject}")
    send_email(subject, html, text)

    # Save pending evaluation context to state
    state["pending_evaluation"] = {
        "session_num": session_num,
        "topic": topic,
        "subtopic": subtopic,
        "article": parsed["article"],
        "writing_task": parsed["writing_task"],
        "date": str(date.today()),
    }
    state["topic_history"].append({"topic": topic, "subtopic": subtopic, "date": str(date.today())})
    state["session_count"] = session_num
    state["last_session_date"] = str(date.today())
    save_state(state)

    print("Done.")


if __name__ == "__main__":
    main()
