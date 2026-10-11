"""Password strength analysis.

The password is analyzed in memory only. `analyze()` returns derived features
(length, character classes, detected patterns) so that the raw password never
needs to be stored or sent anywhere else.
"""

import math
import re
import string
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from app.questions import AUTO_CHECKS_BY_ID, QUESTIONS, QUESTIONS_BY_ID

# Bump this whenever the scoring logic changes, so stored records can be
# compared across versions.
SCORING_VERSION = "1.5.0"

# Assumed attacker speed for an offline attack on a fast hash.
GUESSES_PER_SECOND = 1e10

# Number of entropy bits that maps to a base score of 100.
BITS_FOR_FULL_SCORE = 90

# The 10,000 most common passwords (SecLists, MIT license), lowercase.
COMMON_PASSWORDS = frozenset(
    (Path(__file__).parent / "wordlists" / "common-passwords.txt").read_text().split()
)

# Shortest common password that counts when found inside a longer password.
MIN_COMMON_WORD_LENGTH = 5

KEYBOARD_PATTERNS = [
    "qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890",
    "qazwsx", "1qaz2wsx", "zaq12wsx", "1q2w3e4r",
]

LEET_MAP = str.maketrans({"@": "a", "4": "a", "3": "e", "1": "i", "!": "i",
                          "0": "o", "$": "s", "5": "s", "7": "t"})

# Length suggested by "How to improve".
TARGET_LENGTH = 16

# Weaknesses that editing can't fix: the password should be replaced instead.
REPLACE_PATTERNS = {"common_password", "found_in_breach"}
REPLACE_ANSWERS = {"breached"}

# Patterns fixed by simply removing the offending part.
REMOVABLE_PATTERNS = ["contains_common_word", "keyboard_pattern", "sequence",
                      "repeated_chars", "year", "date"]

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
    # Times seen in known breaches (Have I Been Pwned), or None if not checked.
    breach_count: int | None = None


@dataclass
class Improvement:
    fix: str
    score: int  # score after this fix and all the ones before it


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
    # Step-by-step fixes, most effective first. Filled in by analyze().
    improvements: list[Improvement] = field(default_factory=list)
    # True when the password should be replaced rather than edited.
    replace_recommended: bool = False

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


def _contains_common_password(pw: str) -> bool:
    """True if a common password makes up at least half of `pw`."""
    min_len = max(MIN_COMMON_WORD_LENGTH, (len(pw) + 1) // 2)
    return any(pw[i:j] in COMMON_PASSWORDS
               for i in range(len(pw))
               for j in range(i + min_len, len(pw) + 1))


def detect_patterns(pw: str) -> list[str]:
    patterns: list[str] = []
    normalized = pw.lower().translate(LEET_MAP)

    if pw.lower() in COMMON_PASSWORDS or normalized in COMMON_PASSWORDS:
        patterns.append("common_password")
    elif _contains_common_password(pw.lower()) or _contains_common_password(normalized):
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


def _pool_size(lower: bool, upper: bool, digit: bool, symbol: bool, other: bool) -> int:
    return 26 * lower + 26 * upper + 10 * digit + 33 * symbol + 100 * other


def _entropy(length: int, pool: int) -> float:
    return round(length * math.log2(pool), 2) if pool else 0.0


def extract_features(pw: str) -> Features:
    has_lower = any(c in string.ascii_lowercase for c in pw)
    has_upper = any(c in string.ascii_uppercase for c in pw)
    has_digit = any(c in string.digits for c in pw)
    has_symbol = any(c in string.punctuation or c == " " for c in pw)
    has_other = any(not c.isascii() for c in pw)

    pool = _pool_size(has_lower, has_upper, has_digit, has_symbol, has_other)

    return Features(
        length=len(pw),
        has_lower=has_lower,
        has_upper=has_upper,
        has_digit=has_digit,
        has_symbol=has_symbol,
        has_other=has_other,
        pool_size=pool,
        entropy_bits=_entropy(len(pw), pool),
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


def _raw_score(features: Features, answers: dict[str, bool]) -> tuple[float, list[str], list[str]]:
    """Base score minus penalties (not clamped), with the issues and tips found."""
    base = min(100.0, features.entropy_bits * 100 / BITS_FOR_FULL_SCORE)

    issues: list[str] = []
    tips: list[str] = []
    penalty = 0

    for pattern in features.patterns:
        check = AUTO_CHECKS_BY_ID[pattern]
        penalty += check.penalty
        issues.append(check.issue.format(breach_count=features.breach_count))
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

    return base - penalty, issues, tips


def _clamp(raw: float) -> int:
    return int(round(max(0.0, min(100.0, raw))))


def score_features(features: Features, answers: dict[str, bool]) -> Assessment:
    """Combine password features and yes/no answers into a 0-100 score."""
    raw, issues, tips = _raw_score(features, answers)
    score = _clamp(raw)

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


# A fix transforms (features, answers) as if the user had made that change.
Fix = Callable[[Features, dict[str, bool]], tuple[Features, dict[str, bool]]]


def _add_classes(f: Features, fixed: tuple[str, ...], **classes: bool) -> Features:
    """Copy of `f` with extra character classes and the `fixed` patterns removed."""
    f = replace(f, patterns=[p for p in f.patterns if p not in fixed], **classes)
    f.pool_size = _pool_size(f.has_lower, f.has_upper, f.has_digit, f.has_symbol, f.has_other)
    f.entropy_bits = _entropy(f.length, f.pool_size)
    return f


def _lengthen(f: Features, answers: dict[str, bool]):
    f = replace(f, length=TARGET_LENGTH,
                entropy_bits=_entropy(TARGET_LENGTH, f.pool_size),
                patterns=[p for p in f.patterns if p != "too_short"])
    return f, answers


def _remove_pattern(pattern: str) -> Fix:
    def fix(f: Features, answers: dict[str, bool]):
        f = replace(f, patterns=[p for p in f.patterns if p != pattern])
        # Questions about the same weakness no longer apply either.
        answers = {q: a and pattern not in QUESTIONS_BY_ID[q].overlaps
                   for q, a in answers.items()}
        return f, answers
    return fix


def _answer_no(qid: str) -> Fix:
    return lambda f, answers: (f, {**answers, qid: False})


def _available_fixes(f: Features, answers: dict[str, bool]) -> list[tuple[str, Fix]]:
    fixes: list[tuple[str, Fix]] = []
    if f.length < TARGET_LENGTH:
        fixes.append((AUTO_CHECKS_BY_ID["too_short"].fix, _lengthen))
    if "digits_only" in f.patterns:
        fixes.append((AUTO_CHECKS_BY_ID["digits_only"].fix, lambda f, a: (
            _add_classes(f, ("digits_only",), has_lower=True, has_upper=True), a)))
    if "letters_only" in f.patterns:
        fixes.append((AUTO_CHECKS_BY_ID["letters_only"].fix, lambda f, a: (
            _add_classes(f, ("letters_only",), has_digit=True, has_symbol=True), a)))
    if "single_case" in f.patterns:
        fixes.append((AUTO_CHECKS_BY_ID["single_case"].fix, lambda f, a: (
            _add_classes(f, ("single_case",), has_lower=True, has_upper=True), a)))
    for pattern in REMOVABLE_PATTERNS:
        if pattern in f.patterns:
            fixes.append((AUTO_CHECKS_BY_ID[pattern].fix, _remove_pattern(pattern)))
    for q in QUESTIONS:
        if answers.get(q.id) and not any(p in f.patterns for p in q.overlaps):
            fixes.append((q.fix, _answer_no(q.id)))
    return fixes


def suggest_improvements(assessment: Assessment, answers: dict[str, bool]) -> None:
    """Fill in step-by-step fixes for a scored password.

    Fixes are applied one at a time, always picking the one that helps most
    next, so each step's score includes the steps before it. Unclamped scores
    are compared, so fixes still rank sensibly while the score is stuck at 0.
    """
    f = assessment.features
    if REPLACE_PATTERNS & set(f.patterns) or any(answers.get(q) for q in REPLACE_ANSWERS):
        assessment.replace_recommended = True
        return

    state = (f, answers)
    current = _raw_score(*state)[0]
    remaining = _available_fixes(f, answers)
    while remaining and current < 100:
        options = [(_raw_score(*fix(*state))[0], text, fix) for text, fix in remaining]
        raw, text, fix = max(options, key=lambda o: o[0])
        if raw <= current:
            break
        state, current = fix(*state), raw
        remaining = [(t, x) for t, x in remaining if t != text]
        assessment.improvements.append(Improvement(text, _clamp(raw)))


def analyze(password: str, answers: dict[str, bool],
            breach_count: int | None = None) -> Assessment:
    """Score a password. `breach_count` comes from app.breach (None = unknown)."""
    features = extract_features(password)
    features.breach_count = breach_count
    if breach_count:
        features.patterns.insert(0, "found_in_breach")
    assessment = score_features(features, answers)
    suggest_improvements(assessment, answers)
    return assessment
