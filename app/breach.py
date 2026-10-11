"""Check whether a password appears in known data breaches.

Uses the Have I Been Pwned "Pwned Passwords" range API with k-anonymity:
only the first 5 characters of the password's SHA-1 hash are sent, and the
match is done locally against the returned suffixes. The password itself
never leaves the server.
"""

import hashlib
import logging
import os
import urllib.request

API_URL = "https://api.pwnedpasswords.com/range/"
TIMEOUT_SECONDS = 3

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return os.environ.get("BREACH_CHECK", "true").lower() != "false"


def parse_range(body: str, suffix: str) -> int:
    """Return how often `suffix` appears in a range API response (0 if absent)."""
    for line in body.splitlines():
        candidate, _, count = line.strip().partition(":")
        if candidate.upper() == suffix:
            return int(count)  # padding entries have a count of 0
    return 0


def breach_count(password: str) -> int | None:
    """Number of times the password was seen in breaches, or None if unknown."""
    if not is_enabled():
        return None
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    request = urllib.request.Request(API_URL + prefix, headers={
        "User-Agent": "password-strength-checker",
        "Add-Padding": "true",  # hides the real response size
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return parse_range(response.read().decode("utf-8"), suffix)
    except Exception:  # network errors / timeouts: skip the check
        logger.warning("Breach check failed", exc_info=True)
        return None
