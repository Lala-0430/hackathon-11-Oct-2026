from app.analyzer import analyze, detect_patterns, format_duration


def test_common_password_is_very_weak():
    result = analyze("password", {})
    assert result.score == 0
    assert result.label == "Very Weak"
    assert "common_password" in result.features.patterns


def test_leet_variant_of_common_password_is_detected():
    assert "common_password" in detect_patterns("P@ssw0rd")


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


def test_format_duration():
    assert format_duration(0.5) == "less than a second"
    assert format_duration(120) == "2 minutes"
    assert format_duration(86400) == "1 day"
