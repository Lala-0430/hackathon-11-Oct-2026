import re

from app.analyzer import analyze, detect_patterns, format_duration


def test_common_password_is_very_weak():
    result = analyze("password", {})
    assert result.score == 0
    assert result.label == "Very Weak"
    assert "common_password" in result.features.patterns


def test_leet_variant_of_common_password_is_detected():
    assert "common_password" in detect_patterns("P@ssw0rd")


def test_common_password_list_is_loaded():
    from app.analyzer import COMMON_PASSWORDS

    assert len(COMMON_PASSWORDS) >= 10000
    assert "common_password" in detect_patterns("Mustang")
    assert "common_password" in detect_patterns("password123")


def test_common_password_with_extras_is_detected():
    assert "contains_common_word" in detect_patterns("xxpassword99")
    assert "contains_common_word" in detect_patterns("summer1998")
    assert "contains_common_word" in detect_patterns("$h@d0w!!")


def test_short_common_word_in_long_password_is_not_flagged():
    patterns = detect_patterns("correcthorsebatterystaple")
    assert "common_password" not in patterns
    assert "contains_common_word" not in patterns


def test_long_random_password_is_very_strong():
    result = analyze("t7#Vq!x9Lm@2Rz$Kp4&", {})
    assert result.label == "Very Strong"
    assert result.features.patterns == []


def test_yes_answers_lower_the_score():
    pw = "t7#Vq!x9Lm@2Rz$Kp4&"
    clean = analyze(pw, {"contains_name": False}).score
    with_name = analyze(pw, {"contains_name": True, "reused": True}).score
    assert with_name == clean - 45


def test_sequence_question_not_double_counted():
    detected = analyze("Zr!abc9Kq#2mWx", {})  # "abc" is detected automatically
    assert "sequence" in detected.features.patterns
    assert analyze("Zr!abc9Kq#2mWx", {"predictable_sequence": True}).score == detected.score

    undetected = analyze("t7#Vq!x9Lm@2Rz$Kp4&", {})
    assert analyze("t7#Vq!x9Lm@2Rz$Kp4&", {"predictable_sequence": True}).score == undetected.score - 15


def test_pattern_detection():
    assert "sequence" in detect_patterns("xyabcq")
    assert "keyboard_pattern" in detect_patterns("myqwertpass")
    assert "repeated_chars" in detect_patterns("heyyyy")
    assert "year" in detect_patterns("summer1998")
    assert "digits_only" in detect_patterns("48291736")
    assert "too_short" in detect_patterns("a1!")
    assert "single_case" in detect_patterns("sunflower99")
    assert "single_case" not in detect_patterns("Sunflower99")
    assert "single_case" not in detect_patterns("12345678")
    assert "single_case" not in detect_patterns("こんにちは12345")


def test_format_duration():
    assert format_duration(0.5) == "less than a second"
    assert format_duration(120) == "2 minutes"
    assert format_duration(86400) == "1 day"


def test_every_detectable_pattern_has_an_auto_check():
    import inspect

    from app import analyzer
    from app.questions import AUTO_CHECKS_BY_ID, QUESTIONS

    detected_ids = set(re.findall(r'patterns\.(?:append\(|insert\(0, )"(\w+)"\)', inspect.getsource(analyzer)))
    assert detected_ids == set(AUTO_CHECKS_BY_ID)
    for q in QUESTIONS:
        assert set(q.overlaps) <= set(AUTO_CHECKS_BY_ID)


def test_breach_count_adds_auto_check_and_skips_question():
    pw = "t7#Vq!x9Lm@2Rz$Kp4&"
    breached = analyze(pw, {"breached": True}, breach_count=1234)
    assert "found_in_breach" in breached.features.patterns
    assert breached.features.breach_count == 1234
    assert breached.score == 0
    assert any("1,234 times" in issue for issue in breached.issues)
    assert not any("You answered yes" in issue for issue in breached.issues)


def test_breach_check_unknown_or_clean_changes_nothing():
    pw = "t7#Vq!x9Lm@2Rz$Kp4&"
    for count in (None, 0):
        result = analyze(pw, {}, breach_count=count)
        assert "found_in_breach" not in result.features.patterns
    assert analyze(pw, {"breached": True}, breach_count=0).score == analyze(pw, {}).score - 30
