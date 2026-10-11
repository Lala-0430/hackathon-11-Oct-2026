"""Password strength analysis.

The password is analyzed in memory only. `analyze()` returns derived features
(length, character classes, detected patterns) so that the raw password never
needs to be stored or sent anywhere else.
"""

import math
import re
import string
from dataclasses import asdict, dataclass, field

from app.questions import AUTO_CHECKS_BY_ID, QUESTIONS_BY_ID

# Bump this whenever the scoring logic changes, so stored records can be
# compared across versions.
SCORING_VERSION = "1.2.0"

# Assumed attacker speed for an offline attack on a fast hash.
GUESSES_PER_SECOND = 1e10

# Number of entropy bits that maps to a base score of 100.
BITS_FOR_FULL_SCORE = 90

COMMON_PASSWORDS = {
    "123456", "123456789", "12345678", "12345", "1234567", "1234567890",
    "111111", "000000", "123123", "654321", "666666", "121212", "112233",
    "password", "password1", "password123", "passw0rd", "qwerty", "qwerty123",
    "qwertyuiop", "abc123", "iloveyou", "admin", "welcome", "letmein",
    "monkey", "dragon", "football", "baseball", "sunshine", "princess",
    "master", "shadow", "superman", "batman", "trustno1", "login", "starwars",
    "hello", "freedom", "whatever", "michael", "jennifer", "charlie",
    "secret", "access", "computer", "pokemon", "soccer", "hockey", "killer",
    "ninja", "mustang", "jordan", "hunter", "ranger", "buster", "thomas",
    "tigger", "robert", "summer", "winter", "flower", "cookie", "chocolate",
    "lovely", "angel", "loveme", "zaq12wsx", "1q2w3e4r", "1qaz2wsx",
    "asdfghjkl", "asdf", "zxcvbnm", "qazwsx", "changeme", "default",
}

KEYBOARD_PATTERNS = [
    "qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890",
    "qazwsx", "1qaz2wsx", "zaq12wsx", "1q2w3e4r",
]

LEET_MAP = str.maketrans({"@": "a", "4": "a", "3": "e", "1": "i", "!": "i",
                          "0": "o", "$": "s", "5": "s", "7": "t"})

# (min_score, label)
LABELS = [
    (80, "Very Strong"),
    (60, "Strong"),
    (40, "Fair"),
    (20, "Weak"),
    (0, "Very Weak"),
]


@dataclass
class Features:
    length: int
    has_lower: bool
    has_upper: bool
    has_digit: bool
    has_symbol: bool
    has_other: bool
    pool_size: int
    entropy_bits: float
    patterns: list[str] = field(default_factory=list)


@dataclass
class Assessment:
    score: int
    label: str
    effective_bits: float
    crack_time_seconds: float
    crack_time_display: str
    issues: list[str]
    tips: list[str]
    features: Features

    def to_dict(self) -> dict:
        return asdict(self)


def _has_sequence(pw: str, run: int = 3) -> bool:
    lowered = pw.lower()
    for i in range(len(lowered) - run + 1):
        chunk = lowered[i:i + run]
        if not (chunk.isalnum() and chunk.isascii()):
            continue
        diffs = {ord(chunk[j + 1]) - ord(chunk[j]) for j in range(run - 1)}
        if diffs == {1} or diffs == {-1}:
            return True
    return False


def _has_keyboard_pattern(pw: str, run: int = 4) -> bool:
    lowered = pw.lower()
    for row in KEYBOARD_PATTERNS:
        for candidate in (row, row[::-1]):
            for i in range(len(candidate) - run + 1):
                if candidate[i:i + run] in lowered:
                    return True
    return False


def detect_patterns(pw: str) -> list[str]:
    patterns: list[str] = []
    normalized = pw.lower().translate(LEET_MAP)

    if pw.lower() in COMMON_PASSWORDS or normalized in COMMON_PASSWORDS:
        patterns.append("common_password")
    elif any(len(w) >= 5 and w in normalized for w in COMMON_PASSWORDS):
        patterns.append("contains_common_word")

    if _has_keyboard_pattern(pw):
        patterns.append("keyboard_pattern")
    if _has_sequence(pw):
        patterns.append("sequence")
    if re.search(r"(.)\1\1", pw):
        patterns.append("repeated_chars")
    if re.search(r"(19|20)\d{2}", pw):
        patterns.append("year")
    if re.search(r"(0[1-9]|1[0-2])[-/.]?(0[1-9]|[12]\d|3[01])", pw) and re.search(r"\d{4}", pw):
        patterns.append("date")
    if pw.isalpha():
        patterns.append("letters_only")
    if any(c.islower() or c.isupper() for c in pw) and (pw == pw.lower() or pw == pw.upper()):
        patterns.append("single_case")
    if pw.isdigit():
        patterns.append("digits_only")
    if len(pw) < 8:
        patterns.append("too_short")
    return patterns


def extract_features(pw: str) -> Features:
    has_lower = any(c in string.ascii_lowercase for c in pw)
    has_upper = any(c in string.ascii_uppercase for c in pw)
    has_digit = any(c in string.digits for c in pw)
    has_symbol = any(c in string.punctuation or c == " " for c in pw)
    has_other = any(not c.isascii() for c in pw)

    pool = (26 * has_lower + 26 * has_upper + 10 * has_digit
            + 33 * has_symbol + 100 * has_other)
    entropy = len(pw) * math.log2(pool) if pool else 0.0

    return Features(
        length=len(pw),
        has_lower=has_lower,
        has_upper=has_upper,
        has_digit=has_digit,
        has_symbol=has_symbol,
        has_other=has_other,
        pool_size=pool,
        entropy_bits=round(entropy, 2),
        patterns=detect_patterns(pw),
    )


def _label_for(score: int) -> str:
    for threshold, label in LABELS:
        if score >= threshold:
            return label
    return LABELS[-1][1]


def format_duration(seconds: float) -> str:
    if seconds < 1:
        return "less than a second"
    units = [
        ("century", 100 * 365.25 * 86400),
        ("year", 365.25 * 86400),
        ("month", 30.44 * 86400),
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
        ("second", 1),
    ]
    if seconds >= 1000 * units[0][1]:
        return "centuries"
    for name, size in units:
        if seconds >= size:
            value = int(seconds // size)
            plural = "centuries" if name == "century" else f"{name}s"
            return f"{value} {name if value == 1 else plural}"
    return "less than a second"


def score_features(features: Features, answers: dict[str, bool]) -> Assessment:
    """Combine password features and yes/no answers into a 0-100 score."""
    base = min(100.0, features.entropy_bits * 100 / BITS_FOR_FULL_SCORE)

    issues: list[str] = []
    tips: list[str] = []
    penalty = 0

    for pattern in features.patterns:
        check = AUTO_CHECKS_BY_ID[pattern]
        penalty += check.penalty
        issues.append(check.issue)
        tips.append(check.tip)

    for qid, answer in answers.items():
        question = QUESTIONS_BY_ID.get(qid)
        if not (question and answer):
            continue
        if any(p in features.patterns for p in question.overlaps):
            continue  # already penalized by automatic detection
        penalty += question.penalty
        issues.append(f"You answered yes to: \"{question.text}\"")
        tips.append(question.tip)

    score = int(round(max(0.0, min(100.0, base - penalty))))

    if score >= 80 and not tips:
        tips.append("Great password. Store it in a password manager and enable 2FA.")
    elif not any("password manager" in t for t in tips):
        tips.append("Consider a passphrase of 4+ random words, stored in a password manager.")

    effective_bits = score * BITS_FOR_FULL_SCORE / 100
    crack_seconds = (2 ** effective_bits) / 2 / GUESSES_PER_SECOND

    return Assessment(
        score=score,
        label=_label_for(score),
        effective_bits=round(effective_bits, 2),
        crack_time_seconds=crack_seconds,
        crack_time_display=format_duration(crack_seconds),
        issues=issues,
        tips=tips,
        features=features,
    )


def analyze(password: str, answers: dict[str, bool]) -> Assessment:
    return score_features(extract_features(password), answers)
