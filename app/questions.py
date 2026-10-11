"""Yes/no questions asked after the user enters a password.

Each question captures context that cannot be detected from the password
alone (e.g. whether it contains the user's own name). A "yes" answer applies
the given penalty to the score.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    penalty: int
    tip: str
    # Pattern ids (see analyzer.PATTERN_RULES) that cover the same weakness.
    # If any of them was already detected, this question's penalty is skipped
    # so the weakness is not counted twice.
    overlaps: tuple[str, ...] = ()


QUESTIONS: list[Question] = [
    Question(
        id="contains_name",
        text="Does your password contain your name or nickname?",
        penalty=25,
        tip="Remove your name. It is the first thing an attacker who knows you will try.",
    ),
    Question(
        id="contains_birthday",
        text="Does it contain your date of birth or birth year?",
        penalty=25,
        tip="Remove birth dates. They are easy to find on social media.",
    ),
    Question(
        id="contains_location",
        text="Does it contain the name of your city, town, or street?",
        penalty=15,
        tip="Avoid place names you are connected to. They are easy to guess from your profiles.",
    ),
    Question(
        id="contains_family_or_pet",
        text="Does it contain the name of a family member, friend, partner, or pet?",
        penalty=20,
        tip="Avoid names of people and pets close to you.",
    ),
    Question(
        id="predictable_sequence",
        text="Does it contain a predictable sequence (e.g. 12345, abcdef, qwerty)?",
        penalty=15,
        tip="Avoid sequences and keyboard patterns. They are in every cracking dictionary.",
        overlaps=("sequence", "keyboard_pattern"),
    ),
    Question(
        id="reused",
        text="Do you use the same password for multiple accounts?",
        penalty=20,
        tip="Use a unique password per site. A password manager makes this easy.",
    ),
    Question(
        id="contains_personal_number",
        text="Does it contain a phone number, address number, ZIP code, or ID number?",
        penalty=20,
        tip="Avoid personal numbers. They often appear in leaked databases.",
    ),
    Question(
        id="contains_interest",
        text="Is it based on a favorite team, band, hobby, or brand?",
        penalty=10,
        tip="Interests are guessable from your profiles. Use unrelated random words.",
    ),
    Question(
        id="word_with_substitutions",
        text="Is it a common word with simple substitutions (e.g. p@ssw0rd)?",
        penalty=15,
        tip="Cracking tools try l33t-speak substitutions automatically.",
    ),
    Question(
        id="shared",
        text="Have you ever shared this password with someone else?",
        penalty=10,
        tip="Change passwords you have shared, and avoid sharing them in the future.",
    ),
    Question(
        id="breached",
        text="As far as you know, has this password ever been exposed in a data breach?",
        penalty=30,
        tip="Change any breached password everywhere you use it. Attackers try leaked passwords first.",
    ),
]

QUESTIONS_BY_ID: dict[str, Question] = {q.id: q for q in QUESTIONS}
