import json
import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

STATE_PATH = Path(__file__).parent.parent / "state" / "state.json"

TOPICS = [
    "data science",
    "revenue operations",
    "sales compensation",
]

TOPIC_SUBTOPICS = {
    "data science": [
        "feature engineering",
        "model evaluation metrics",
        "data pipeline design",
        "A/B testing methodology",
        "causal inference",
        "time series forecasting",
        "ML model deployment",
        "data quality and governance",
        "dimensionality reduction",
        "Bayesian methods in practice",
    ],
    "revenue operations": [
        "CRM data hygiene",
        "pipeline forecasting",
        "lead scoring models",
        "sales cycle analysis",
        "revenue attribution",
        "churn prediction",
        "territory planning",
        "quota setting methodologies",
        "go-to-market alignment",
        "RevOps metrics and KPIs",
    ],
    "sales compensation": [
        "commission plan design",
        "SPIFs and accelerators",
        "quota attainment analysis",
        "pay mix and OTE",
        "clawback policies",
        "sales performance incentive plans",
        "compensation benchmarking",
        "non-recoverable draws",
        "MBO-based compensation",
        "multi-product commission stacking",
    ],
}

WRITING_TASK_TYPES_BY_LEVEL = {
    1: [
        "Write 2–3 sentences summarizing the main argument of the text.",
        "Write 2–3 sentences describing one concept from the text in your own words.",
        "Write 2–3 sentences explaining what you found most interesting and why.",
    ],
    2: [
        "Write a short paragraph (4–6 sentences) summarizing the key points of the text.",
        "Write a short paragraph (4–6 sentences) explaining how the concept applies to your current work.",
        "Write a short paragraph (4–6 sentences) identifying one limitation of the approach described.",
    ],
    3: [
        "Write a paragraph (6–8 sentences) arguing for or against the main claim in the text.",
        "Write a paragraph (6–8 sentences) comparing the approach described with an alternative you know.",
        "Draft a short internal Slack message (6–8 sentences) explaining this concept to a colleague.",
    ],
    4: [
        "Draft a professional email (150–200 words) to a stakeholder explaining the key finding and its business implication.",
        "Write an executive summary paragraph (150–200 words) of the text, suitable for a non-technical manager.",
        "Write a critical analysis (150–200 words) evaluating the strengths and weaknesses of the approach.",
    ],
    5: [
        "Draft a professional email (200–250 words) proposing a change based on the insights from the text, including a call to action.",
        "Write a structured argument (200–250 words) either defending or challenging the text's main recommendation, citing specific evidence.",
        "Draft an executive briefing document (200–250 words) with sections: Background, Key Finding, Recommendation, and Next Steps.",
    ],
}


def load_state() -> dict:
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def pick_topic(state: dict) -> tuple[str, str]:
    """Pick the next topic+subtopic, rotating to avoid recent repetition."""
    history = state.get("topic_history", [])
    recent = [h["subtopic"] for h in history[-9:]] if history else []

    for topic in TOPICS:
        for subtopic in TOPIC_SUBTOPICS[topic]:
            if subtopic not in recent:
                return topic, subtopic

    # All subtopics used — start over
    topic = TOPICS[len(history) % len(TOPICS)]
    subtopic = TOPIC_SUBTOPICS[topic][0]
    return topic, subtopic


def get_writing_task_prompt(writing_level: int) -> str:
    level = max(1, min(5, writing_level))
    import random
    tasks = WRITING_TASK_TYPES_BY_LEVEL[level]
    return random.choice(tasks)


def should_include_error_review(state: dict) -> bool:
    """Every 7 sessions, include a review of recurring errors."""
    return (
        state.get("session_count", 0) % 7 == 6
        and bool(state.get("recurring_errors"))
    )


def send_email(subject: str, html_body: str, text_body: str) -> None:
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    recipient = os.environ["RECIPIENT_EMAIL"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = recipient

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipient, msg.as_string())


def update_scores_and_level(state: dict, scores: dict) -> dict:
    """
    Update recent_writing_scores and adjust writing_level.
    scores: {"grammar": 1-5, "semantics": 1-5, "fluency": 1-5}
    """
    avg = sum(scores.values()) / len(scores)
    recent = state.get("recent_writing_scores", [])
    recent.append({"date": str(date.today()), "scores": scores, "avg": round(avg, 2)})

    # Keep only last 10 sessions
    recent = recent[-10:]
    state["recent_writing_scores"] = recent

    # Progression logic (based on last 5 sessions)
    if len(recent) >= 5:
        last5_avgs = [s["avg"] for s in recent[-5:]]
        last5_mean = sum(last5_avgs) / 5

        current_level = state.get("writing_level", 1)
        if last5_mean >= 4.0 and current_level < 5:
            state["writing_level"] = current_level + 1
        elif last5_mean < 3.0:
            # Check if last 3 are all below 3.0
            if len(recent) >= 3 and all(s["avg"] < 3.0 for s in recent[-3:]):
                state["writing_level"] = max(1, current_level - 1)

    return state
