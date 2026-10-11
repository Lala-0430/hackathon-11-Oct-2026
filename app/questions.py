"""All scoring rules: yes/no questions and automatic checks.

- QUESTIONS are asked after the user enters a password. They capture context
  that cannot be detected from the password alone (e.g. whether it contains
  the user's own name). A "yes" answer applies the given penalty.
- AUTO_CHECKS are detected from the password itself by app/analyzer.py,
  so the user is not asked about them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    penalty: int
    tip: str
    # Short action shown in "How to improve", e.g. "Remove your name".
    fix: str
    # AutoCheck ids (see AUTO_CHECKS below) that cover the same weakness.
    # If any of them was already detected, this question's penalty is skipped
    # so the weakness is not counted twice.
    overlaps: tuple[str, ...] = ()


QUESTIONS: list[Question] = [
    Question(
        id="contains_name",
        text="Does your password contain your name or nickname?",
        penalty=25,
        tip="Names are one of the first things someone tries when guessing a password.",
        fix="Remove your name or nickname",
    ),
    Question(
        id="contains_birthday",
        text="Does your password contain your date of birth or birth year?",
        penalty=25,
        tip="Birth dates and years are easy to find online and are among the most common guesses.",
        fix="Remove your birth date or year",
    ),
    Question(
        id="contains_location",
        text="Does your password contain your city, town or street name?",
        penalty=15,
        tip="Places connected to you can often be found on your social media or public profiles.",
        fix="Remove the place name",
    ),
    Question(
        id="contains_family_or_pet",
        text="Does it contain the name of a family member, friend, partner or pet?",
        penalty=20,
        tip="People close to you are easy to find on social media, which makes their names easy to guess.",
        fix="Remove the name of someone close to you",
    ),
    Question(
        id="predictable_sequence",
        text="Does it contain a predictable sequence or repeats, like 12345, abcdef, qwerty or aaa?",
        penalty=15,
        tip="Sequences and keyboard patterns are in every attacker's guessing list.",
        fix="Remove the sequence or repeats",
        overlaps=("sequence", "keyboard_pattern", "repeated_chars"),
    ),
    Question(
        id="reused",
        text="Do you use this same password on other websites or accounts?",
        penalty=20,
        tip="If one site is breached, attackers try that same password on your other accounts.",
        fix="Use it on this account only",
    ),
    Question(
        id="contains_personal_number",
        text="Does it contain a phone number, house number, postcode or ID number?",
        penalty=20,
        tip="Numbers connected to you are easy to find or guess, so they add very little protection.",
        fix="Remove the personal number",
    ),
    Question(
        id="contains_interest",
        text="Is it based on a favourite team, band, hobby or brand?",
        penalty=10,
        tip="Your interests are often visible online, which makes them easier to guess.",
        fix="Remove the team, band, hobby or brand",
    ),
    Question(
        id="word_with_substitutions",
        text="Is it a normal word with simple swaps, like a changed to @ or o changed to 0?",
        penalty=15,
        tip="Attackers know these swaps well, so they don't make a word much harder to guess.",
        fix="Replace the word with random words or characters",
    ),
    Question(
        id="shared",
        text="Have you shared this password with anyone else?",
        penalty=10,
        tip="Once a password is shared, you can no longer control who else has it.",
        fix="Stop sharing it and keep it to yourself",
    ),
    Question(
        id="breached",
        text="Has this password ever appeared in a data breach, for example in a breach alert?",
        penalty=30,
        tip="A password that has leaked once is in attackers' lists and should never be used again.",
        fix="Replace it with a password that has never leaked",
        overlaps=("found_in_breach",),
    ),
]

QUESTIONS_BY_ID: dict[str, Question] = {q.id: q for q in QUESTIONS}


@dataclass(frozen=True)
class AutoCheck:
    id: str
    issue: str
    penalty: int
    tip: str
    fix: str


# The detection logic for each id lives in analyzer.detect_patterns(), except
# found_in_breach, which comes from app/breach.py (see analyzer.analyze()).
# `issue` may use {breach_count}.
AUTO_CHECKS: list[AutoCheck] = [
    AutoCheck(
        id="found_in_breach",
        issue="It appears in known data breaches (seen {breach_count:,} times).",
        penalty=100,
        tip="Leaked passwords are in every attacker's list. Never use this one again, "
            "and change it anywhere you still use it.",
        fix="Replace it with a password that has never leaked",
    ),
    AutoCheck(
        id="common_password",
        issue="This is one of the most common passwords.",
        penalty=100,
        tip="Very common passwords are the first ones attackers try, so change this one straight away.",
        fix="Replace it with something unique",
    ),
    AutoCheck(
        id="contains_common_word",
        issue="It is a common password with a few extra characters added.",
        penalty=20,
        tip="Adding a number or symbol to a common word barely slows attackers down, "
            "because they try those variations automatically.",
        fix="Remove the common password inside it",
    ),
    AutoCheck(
        id="too_short",
        issue="It is shorter than 8 characters.",
        penalty=20,
        tip="Short passwords can be guessed far faster. Use at least 12 characters.",
        fix="Make it at least 16 characters long",
    ),
    AutoCheck(
        id="digits_only",
        issue="It uses digits only.",
        penalty=20,
        tip="Digits alone give attackers very few combinations to try.",
        fix="Add letters",
    ),
    AutoCheck(
        id="letters_only",
        issue="It uses letters only, with no numbers or symbols.",
        penalty=10,
        tip="Mixing in numbers and symbols gives attackers more combinations to get through.",
        fix="Add numbers and symbols",
    ),
    AutoCheck(
        id="single_case",
        issue="Its letters are all lowercase or all uppercase.",
        penalty=10,
        tip="Mixing upper and lower case makes a password harder to guess.",
        fix="Mix upper and lower case",
    ),
    AutoCheck(
        id="keyboard_pattern",
        issue="It contains a keyboard pattern (e.g. 'qwerty', 'asdf').",
        penalty=15,
        tip="Avoid keyboard walks. They are in every cracking dictionary.",
        fix="Remove the keyboard pattern",
    ),
    AutoCheck(
        id="sequence",
        issue="It contains a sequence like 'abc' or '123'.",
        penalty=10,
        tip="Avoid alphabetical or numeric sequences.",
        fix="Remove the sequence",
    ),
    AutoCheck(
        id="repeated_chars",
        issue="It contains repeated characters (e.g. 'aaa').",
        penalty=10,
        tip="Avoid repeating the same character.",
        fix="Remove the repeated characters",
    ),
    AutoCheck(
        id="year",
        issue="It contains something that looks like a year.",
        penalty=10,
        tip="Avoid years. Attackers try 1900-2099 automatically.",
        fix="Remove the year",
    ),
    AutoCheck(
        id="date",
        issue="It contains something that looks like a date.",
        penalty=10,
        tip="Avoid dates such as birthdays or anniversaries.",
        fix="Remove the date",
    ),
]

AUTO_CHECKS_BY_ID: dict[str, AutoCheck] = {c.id: c for c in AUTO_CHECKS}
