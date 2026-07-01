"""
Submit your written response for evaluation.

Usage:
    python scripts/submit_response.py

Paste your response when prompted (Ctrl+D or Ctrl+Z on Windows to finish),
or provide it as a file: python scripts/submit_response.py --file my_answer.txt
"""

import argparse
import os
import sys
from datetime import date

import anthropic

sys.path.insert(0, os.path.dirname(__file__))
from utils import load_state, save_state, update_scores_and_level

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
    scores_raw = sections.get("---SCORES---", "")
    for line in scores_raw.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            try:
                scores[key.strip()] = int(val.strip())
            except ValueError:
                pass

    new_errors = []
    errors_raw = sections.get("---RECURRING ERRORS---", "")
    for line in errors_raw.splitlines():
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


def print_evaluation(ev: dict, state: dict) -> None:
    scores = ev["scores"]
    avg = sum(scores.values()) / len(scores) if scores else 0

    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(f"\nSCORES (1–5):")
    print(f"  Grammar:   {scores.get('grammar', '?')}/5")
    print(f"  Semantics: {scores.get('semantics', '?')}/5")
    print(f"  Fluency:   {scores.get('fluency', '?')}/5")
    print(f"  Average:   {avg:.1f}/5")

    wl = state.get("writing_level", 1)
    new_wl = state.get("writing_level", 1)  # updated by update_scores_and_level
    if new_wl > wl:
        print(f"\n  ★ Writing level UP: {wl} → {new_wl}")
    elif new_wl < wl:
        print(f"\n  ↓ Writing level DOWN: {wl} → {new_wl} (keep practicing!)")

    print(f"\n{'─'*60}")
    print("GRAMMAR FEEDBACK")
    print(ev["grammar_feedback"])

    print(f"\n{'─'*60}")
    print("SEMANTICS FEEDBACK")
    print(ev["semantics_feedback"])

    print(f"\n{'─'*60}")
    print("FLUENCY FEEDBACK")
    print(ev["fluency_feedback"])

    print(f"\n{'─'*60}")
    print("SUGGESTED REWRITE")
    print(ev["suggested_rewrite"])

    if ev["new_errors"]:
        print(f"\n{'─'*60}")
        print("PATTERNS TO WATCH (added to your profile):")
        for e in ev["new_errors"]:
            print(f"  • {e}")

    print("=" * 60)


def read_response_from_stdin() -> str:
    print("\nPaste your response below.")
    print("When finished, press Enter, then Ctrl+Z (Windows) or Ctrl+D (Mac/Linux), then Enter.\n")
    lines = []
    try:
        for line in sys.stdin:
            lines.append(line)
    except EOFError:
        pass
    return "".join(lines).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Path to a text file containing your response")
    args = parser.parse_args()

    state = load_state()

    pending = state.get("pending_evaluation")
    if not pending:
        print("No pending evaluation found. Run generate_and_send.py first.")
        sys.exit(1)

    print(f"\n=== Session #{pending['session_num']} — {pending['subtopic'].title()} ===")
    print(f"\nWRITING TASK REMINDER:\n{pending['writing_task']}\n")

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            student_response = f.read().strip()
        print(f"Read response from {args.file}")
    else:
        student_response = read_response_from_stdin()

    if not student_response:
        print("Empty response — aborting.")
        sys.exit(1)

    print("\nEvaluating your response...")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": EVALUATION_PROMPT.format(
                    topic=pending["topic"],
                    subtopic=pending["subtopic"],
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

    raw = message.content[0].text
    ev = parse_evaluation(raw)

    # Update state
    old_writing_level = state["writing_level"]
    state = update_scores_and_level(state, ev["scores"])

    # Merge new recurring errors (keep last 10 unique)
    existing = state.get("recurring_errors", [])
    for err in ev["new_errors"]:
        if err not in existing:
            existing.append(err)
    state["recurring_errors"] = existing[-10:]

    state["pending_evaluation"] = None
    save_state(state)

    print_evaluation(ev, {**state, "writing_level": old_writing_level})


if __name__ == "__main__":
    main()
