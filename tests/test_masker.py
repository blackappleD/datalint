"""masker 模块单元测试: --mask 规则解析、字段匹配与掩码算法."""

import pytest

from datalint.masker import MaskRule, apply_mask, parse_mask_rules


# ---------- 规则解析 ----------


def test_single_pattern_defaults_to_equal():
    rules = parse_mask_rules(["email"])

    assert rules == (MaskRule("email", "equal"),)


def test_pattern_with_contain_mode():
    rules = parse_mask_rules(["phone:contain"])

    assert rules == (MaskRule("phone", "contain"),)


def test_repeated_options_and_comma_merge():
    rules = parse_mask_rules(["email:equal,phone:contain", "ssn"])

    assert rules == (
        MaskRule("email", "equal"),
        MaskRule("phone", "contain"),
        MaskRule("ssn", "equal"),
    )


def test_invalid_mode_raises_with_mode_name():
    with pytest.raises(ValueError) as exc_info:
        parse_mask_rules(["email:fuzzy"])

    assert "fuzzy" in str(exc_info.value)


def test_empty_pattern_variants_raise():
    for raw in [","], [":equal"], [""], ["  "]:
        with pytest.raises(ValueError):
            parse_mask_rules(raw)


def test_none_input_yields_no_rules():
    assert parse_mask_rules(None) == ()


# ---------- 字段匹配 ----------


def test_equal_is_case_sensitive_exact():
    rule = MaskRule("phone", "equal")

    assert rule.matches("phone")
    assert not rule.matches("Phone")
    assert not rule.matches("home_phone")


def test_contain_is_case_insensitive_substring():
    rule = MaskRule("phone", "contain")

    assert rule.matches("phone")
    assert rule.matches("home_phone")
    assert rule.matches("PhoneNumber")
    assert not rule.matches("email")


# ---------- 掩码应用 ----------


def test_mask_keeps_first_and_last_char():
    record = {"email": "alice@example.com"}

    masked = apply_mask(record, parse_mask_rules(["email"]))

    value = masked["email"]
    assert value[0] == "a" and value[-1] == "m"
    assert set(value[1:-1]) == {"*"}
    assert len(value) == len("alice@example.com")


def test_short_values_fully_masked():
    rules = parse_mask_rules(["v"])

    assert apply_mask({"v": "abcd"}, rules)["v"] == "****"
    assert apply_mask({"v": "ab"}, rules)["v"] == "**"
    assert apply_mask({"v": "a"}, rules)["v"] == "*"


def test_empty_string_stays_empty():
    assert apply_mask({"v": ""}, parse_mask_rules(["v"]))["v"] == ""


def test_five_char_value_masks_middle():
    assert apply_mask({"v": "abcde"}, parse_mask_rules(["v"]))["v"] == "a***e"


def test_non_string_values_untouched():
    record = {"score": 95, "flag": True, "data": None}

    masked = apply_mask(record, parse_mask_rules(["score", "flag", "data"]))

    assert masked == record


def test_unmatched_fields_untouched():
    record = {"email": "alice@example.com", "name": "Alice"}

    masked = apply_mask(record, parse_mask_rules(["email"]))

    assert masked["name"] == "Alice"


def test_schema_unknown_fields_participate():
    record = {"home_phone": "01088886666"}

    masked = apply_mask(record, parse_mask_rules(["phone:contain"]))

    assert masked["home_phone"] == "0*********6"


def test_apply_mask_returns_new_dict():
    record = {"email": "alice@example.com"}

    masked = apply_mask(record, parse_mask_rules(["email"]))

    assert masked is not record
    assert record["email"] == "alice@example.com"


def test_no_rules_returns_record_unchanged():
    record = {"email": "alice@example.com"}

    assert apply_mask(record, ()) == record
