"""Optional AI advice from Gemma via the Gemini API.

Only the stored, derived features and answers are sent to the model.
The raw password is never sent.
"""

import json
import os

from google import genai

from app.questions import QUESTIONS_BY_ID

MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-26b-a4b-it")

PROMPT_TEMPLATE = """You are a friendly password security coach.
A user checked a password. You do NOT see the password itself, only this analysis:

- Length: {length}
- Character classes: {classes}
- Estimated entropy: {entropy_bits} bits
- Detected patterns: {patterns}
- User answered YES to: {yes_answers}
- Final score: {score}/100 ({label})

Write 3 short, concrete, encouraging tips (one sentence each, as a bulleted
list) to help this user create a stronger password. Do not ask for the password.
"""


def is_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def build_prompt(record: dict) -> str:
    classes = [name for key, name in [
        ("has_lower", "lowercase"), ("has_upper", "uppercase"),
        ("has_digit", "digits"), ("has_symbol", "symbols"),
        ("has_other", "non-ASCII"),
    ] if record[key]]
    yes_answers = [QUESTIONS_BY_ID[q].text for q, a in record["answers"].items()
                   if a and q in QUESTIONS_BY_ID]
    return PROMPT_TEMPLATE.format(
        length=record["length"],
        classes=", ".join(classes) or "none",
        entropy_bits=record["entropy_bits"],
        patterns=json.dumps(record["patterns"]),
        yes_answers="; ".join(yes_answers) or "nothing",
        score=record["score"],
        label=record["label"],
    )


async def get_advice(record: dict) -> str:
    client = genai.Client()  # reads GEMINI_API_KEY from the environment
    response = await client.aio.models.generate_content(
        model=MODEL, contents=build_prompt(record)
    )
    return response.text or ""
