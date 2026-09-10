"""cleaner 模块单元测试: 去空白、时间戳归一、按字段去重(按内置默认 SCHEMA)."""

from datalint import cleaner
from datalint.cleaner import Deduplicator, normalize_timestamp
from datalint.schema import DUPLICATE, SCHEMA, TIMESTAMP_INVALID, Rejection


def clean(line_no, record):
    return cleaner.clean(line_no, record, SCHEMA)


def record_with(**overrides):
    record = {
        "id": "1",
        "name": "Alice",
        "category": "A",
        "timestamp": "2026-09-10T08:00:00Z",
    }
    record.update(overrides)
    return record


# ---------- 去除首尾空白 ----------


def test_string_fields_are_stripped():
    cleaned = clean(1, record_with(name="  Alice  "))

    assert cleaned["name"] == "Alice"


def test_inner_whitespace_is_preserved():
    cleaned = clean(1, record_with(name="  Alice   Smith  "))

    assert cleaned["name"] == "Alice   Smith"


def test_unknown_string_fields_are_also_stripped():
    cleaned = clean(1, record_with(extra="  x  "))

    assert cleaned["extra"] == "x"


def test_non_string_values_untouched():
    cleaned = clean(1, record_with(score=1.5, tags=[1, 2]))

    assert cleaned["score"] == 1.5
    assert cleaned["tags"] == [1, 2]


def test_clean_returns_new_dict_without_mutating_original():
    original = record_with(name="  Alice  ")

    cleaned = clean(1, original)

    assert cleaned is not original
    assert original["name"] == "  Alice  "


# ---------- 时间戳归一化 ----------


def test_iso_with_z_suffix():
    assert normalize_timestamp("2026-09-10T08:00:00Z") == "2026-09-10T08:00:00Z"


def test_iso_with_offset_converted_to_utc():
    assert normalize_timestamp("2026-09-10T16:00:00+08:00") == "2026-09-10T08:00:00Z"


def test_iso_without_timezone_treated_as_utc():
    assert normalize_timestamp("2026-09-10T08:00:00") == "2026-09-10T08:00:00Z"


def test_slash_format():
    assert normalize_timestamp("2026/09/10 08:00:00") == "2026-09-10T08:00:00Z"


def test_unix_seconds_int():
    assert normalize_timestamp(1789027200) == "2026-09-10T08:00:00Z"


def test_unix_seconds_float():
    assert normalize_timestamp(1789027200.0) == "2026-09-10T08:00:00Z"


def test_unix_seconds_numeric_string():
    assert normalize_timestamp("1789027200") == "2026-09-10T08:00:00Z"


def test_unrecognizable_returns_none():
    assert normalize_timestamp("昨天下午") is None
    assert normalize_timestamp("10/09/2026") is None


def test_clean_rejects_bad_timestamp():
    result = clean(7, record_with(timestamp="昨天"))

    assert isinstance(result, Rejection)
    assert result.line == 7
    assert result.error_type == TIMESTAMP_INVALID
    assert "timestamp" in result.reason


def test_timestamp_with_surrounding_whitespace_is_normalized():
    cleaned = clean(1, record_with(timestamp="  2026-09-10T08:00:00Z  "))

    assert cleaned["timestamp"] == "2026-09-10T08:00:00Z"


# ---------- 去重 ----------


def test_dedup_keeps_first_occurrence():
    dedup = Deduplicator(("id",))
    first = record_with(id="1")
    second = record_with(id="1", name="Bob")

    assert dedup.check(1, first) is None
    rejection = dedup.check(2, second)

    assert isinstance(rejection, Rejection)
    assert rejection.error_type == DUPLICATE
    assert rejection.line == 2


def test_dedup_multiple_fields():
    dedup = Deduplicator(("name", "category"))

    assert dedup.check(1, record_with(name="A", category="A")) is None
    assert dedup.check(2, record_with(name="A", category="B")) is None
    assert dedup.check(3, record_with(name="A", category="A")) is not None


def test_dedup_missing_optional_field_skips_dedup():
    # BUG-003: 缺失去重字段不构成"内容相同"的证据 → 跳过去重, 全部保留
    dedup = Deduplicator(("score",))
    no_score_1 = record_with()
    no_score_2 = record_with(name="Bob")

    assert dedup.check(1, no_score_1) is None
    assert dedup.check(2, no_score_2) is None


def test_no_dedup_fields_means_no_dedup():
    dedup = Deduplicator(())

    assert dedup.check(1, record_with(id="1")) is None
    assert dedup.check(2, record_with(id="1")) is None


def test_dedup_applies_after_cleaning():
    # 清洗后 " a " 与 "a" 应判为重复
    dedup = Deduplicator(("name",))
    first = clean(1, record_with(name=" a "))
    second = clean(2, record_with(name="a"))

    assert dedup.check(1, first) is None
    assert dedup.check(2, second) is not None


# ---------- BUG-001: 亚秒精度保留 ----------


def test_subsecond_precision_preserved():
    assert (
        normalize_timestamp("2026-09-11T10:00:00.123Z") == "2026-09-11T10:00:00.123Z"
    )
    assert (
        normalize_timestamp("2026-09-11T10:00:00.456Z") == "2026-09-11T10:00:00.456Z"
    )


def test_subsecond_trailing_zeros_stripped():
    assert normalize_timestamp("2026-09-11T10:00:00.100000Z") == "2026-09-11T10:00:00.1Z"


def test_zero_microseconds_keeps_second_precision():
    assert normalize_timestamp("2026-09-11T10:00:00.000Z") == "2026-09-11T10:00:00Z"


def test_unix_float_fraction_preserved():
    assert normalize_timestamp(1789027200.5) == "2026-09-10T08:00:00.5Z"


def test_dedup_by_timestamp_distinguishes_subseconds():
    dedup = Deduplicator(("timestamp",))
    first = clean(1, record_with(timestamp="2026-09-11T10:00:00.123Z"))
    second = clean(2, record_with(timestamp="2026-09-11T10:00:00.456Z"))

    assert dedup.check(1, first) is None
    assert dedup.check(2, second) is None  # 不同时刻不得误判重复


# ---------- BUG-003: 去重字段缺失跳过去重 ----------


def test_dedup_missing_field_records_all_kept():
    dedup = Deduplicator(("score",))
    no_score_1 = record_with()
    no_score_2 = record_with(name="Bob")
    no_score_3 = record_with(name="Carol")

    # 缺失去重字段的记录跳过去重, 全部保留
    assert dedup.check(1, no_score_1) is None
    assert dedup.check(2, no_score_2) is None
    assert dedup.check(3, no_score_3) is None


def test_dedup_missing_field_does_not_register_key():
    dedup = Deduplicator(("score",))

    assert dedup.check(1, record_with()) is None  # 缺失: 跳过
    assert dedup.check(2, record_with(score=1.0)) is None  # 有值: 首现
    assert dedup.check(3, record_with(score=1.0)) is not None  # 有值重复: 剔除


def test_dedup_partial_missing_in_multi_fields_skips():
    dedup = Deduplicator(("id", "score"))

    assert dedup.check(1, record_with(id="1")) is None  # score 缺失 → 跳过
    assert dedup.check(2, record_with(id="1")) is None  # 同样跳过, 不判重


# ---------- BUG-004: naive 时间戳计数 ----------


def test_naive_timestamps_counted():
    from datalint.cleaner import CleanStats

    stats = CleanStats()
    cleaner.clean(1, record_with(timestamp="2026-09-11T10:00:00"), SCHEMA, stats)
    cleaner.clean(2, record_with(timestamp="2026/09/11 10:00:00"), SCHEMA, stats)
    cleaner.clean(3, record_with(timestamp="2026-09-11T10:00:00+08:00"), SCHEMA, stats)
    cleaner.clean(4, record_with(timestamp=1789027200), SCHEMA, stats)

    # 前两条无时区(ISO 无时区/斜杠格式), 后两条不算
    assert stats.naive_timestamps == 2


# ---------- BUG-006: 可选时间戳字段显式 null ----------


def test_optional_timestamp_null_skips_normalization():
    from datalint.schema import FieldSpec, TYPE_TIMESTAMP

    schema = (FieldSpec("ts", TYPE_TIMESTAMP, required=False),)
    cleaned = cleaner.clean(1, {"ts": None}, schema)

    assert not isinstance(cleaned, Rejection)
    assert cleaned["ts"] is None
