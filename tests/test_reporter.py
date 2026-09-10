"""reporter 模块单元测试: 统计聚合与 JSON/表格渲染."""

import json

from datalint.reporter import Report, render_json, render_table
from datalint.schema import (
    ALL_ERROR_TYPES,
    DUPLICATE,
    ENUM_ERROR,
    MISSING_FIELD,
    PARSE_ERROR,
)


def sample_report():
    report = Report()
    for _ in range(3):
        report.count_pass()
    report.count_reject(PARSE_ERROR)
    report.count_reject(MISSING_FIELD)
    report.count_reject(MISSING_FIELD)
    report.count_reject(DUPLICATE)
    return report


# ---------- 聚合 ----------


def test_counts_accumulate():
    report = sample_report()

    assert report.total == 7
    assert report.passed == 3
    assert report.rejected == 4
    assert report.errors[MISSING_FIELD] == 2
    assert report.errors[PARSE_ERROR] == 1
    assert report.errors[ENUM_ERROR] == 0


def test_invariants_hold():
    report = sample_report()

    assert report.total == report.passed + report.rejected
    assert report.rejected == sum(report.errors.values())


def test_empty_report_is_all_zero():
    report = Report()

    assert report.total == 0
    assert report.passed == 0
    assert report.rejected == 0
    assert all(count == 0 for count in report.errors.values())


# ---------- JSON 渲染 ----------


def test_json_contains_all_error_keys_even_when_zero():
    payload = json.loads(render_json(Report()))

    assert payload["total"] == 0
    assert set(payload["errors"].keys()) == set(ALL_ERROR_TYPES)
    assert all(v == 0 for v in payload["errors"].values())


def test_json_key_order_is_fixed():
    payload = json.loads(render_json(sample_report()))

    assert list(payload.keys()) == ["total", "passed", "rejected", "errors"]
    assert list(payload["errors"].keys()) == list(ALL_ERROR_TYPES)


def test_json_numbers_match_report():
    report = sample_report()
    payload = json.loads(render_json(report))

    assert payload["total"] == 7
    assert payload["passed"] == 3
    assert payload["rejected"] == 4
    assert payload["errors"]["missing_field"] == 2


# ---------- 表格渲染 ----------


def test_table_contains_summary_and_error_sections():
    text = render_table(sample_report())

    assert "datalint report" in text
    assert "total" in text
    assert "passed" in text
    assert "rejected" in text
    for error_type in ALL_ERROR_TYPES:
        assert error_type in text


def test_table_numbers_are_right_aligned():
    text = render_table(sample_report())
    lines = text.splitlines()

    error_lines = [l for l in lines if l.startswith(ALL_ERROR_TYPES)]
    assert len(error_lines) == len(ALL_ERROR_TYPES)
    # 每行数字列结束于同一列位置(右对齐)
    assert len({len(l) for l in error_lines}) == 1


def test_table_and_json_numbers_agree():
    report = sample_report()
    payload = json.loads(render_json(report))
    table = render_table(report)

    for error_type, count in payload["errors"].items():
        matching = [
            l for l in table.splitlines() if l.startswith(error_type)
        ]
        assert matching[0].split()[-1] == str(count)
