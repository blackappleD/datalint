"""reader 模块单元测试: 格式识别、JSONL/CSV 流式读取与解析."""

import pytest

from datalint.reader import FormatDetectionError, detect_format, read_csv, read_jsonl
from datalint.schema import PARSE_ERROR, SCHEMA, Rejection


def test_valid_lines_yield_line_number_and_record(write_jsonl):
    path = write_jsonl([{"id": "1"}, {"id": "2"}])

    items = list(read_jsonl(path))

    assert items == [(1, {"id": "1"}), (2, {"id": "2"})]


def test_invalid_json_yields_parse_error_with_raw_text(write_jsonl):
    path = write_jsonl([{"id": "1"}, "not valid json"])

    items = list(read_jsonl(path))

    assert items[0] == (1, {"id": "1"})
    rejection = items[1]
    assert isinstance(rejection, Rejection)
    assert rejection.line == 2
    assert rejection.error_type == PARSE_ERROR
    assert rejection.record == "not valid json"
    assert rejection.reason


def test_blank_lines_are_skipped_without_counting(write_jsonl):
    path = write_jsonl([{"id": "1"}, "", "   ", {"id": "2"}])

    items = list(read_jsonl(path))

    # 空白行跳过, 但行号仍按物理行计
    assert items == [(1, {"id": "1"}), (4, {"id": "2"})]


def test_non_object_json_is_parse_error(write_jsonl):
    path = write_jsonl(["[1, 2]", '"just a string"', "42"])

    items = list(read_jsonl(path))

    assert len(items) == 3
    for rejection in items:
        assert isinstance(rejection, Rejection)
        assert rejection.error_type == PARSE_ERROR


def test_empty_file_yields_nothing(write_jsonl):
    path = write_jsonl([])

    assert list(read_jsonl(path)) == []


def test_utf8_content_reads_correctly(write_jsonl):
    path = write_jsonl([{"id": "1", "name": "张三"}])

    items = list(read_jsonl(path))

    assert items[0][1]["name"] == "张三"


# ---------- 格式自动识别 ----------


def test_explicit_format_returned_directly(tmp_path):
    path = tmp_path / "whatever.bin"
    path.write_text("anything", encoding="utf-8")

    assert detect_format(path, "csv") == "csv"
    assert detect_format(path, "jsonl") == "jsonl"


def test_extension_detection_case_insensitive(tmp_path):
    for name, expected in [
        ("a.csv", "csv"),
        ("b.CSV", "csv"),
        ("c.jsonl", "jsonl"),
        ("d.JSON", "jsonl"),
    ]:
        path = tmp_path / name
        path.write_text("irrelevant", encoding="utf-8")
        assert detect_format(path, None) == expected


def test_sniff_json_object_line_as_jsonl(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text('{"id": "1"}\n', encoding="utf-8")

    assert detect_format(path, None) == "jsonl"


def test_sniff_csv_header_as_csv(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("id,name,category\n1,Alice,A\n", encoding="utf-8")

    assert detect_format(path, None) == "csv"


def test_empty_file_cannot_be_detected(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    with pytest.raises(FormatDetectionError):
        detect_format(path, None)


def test_undetectable_content_raises(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("just some plain words\n", encoding="utf-8")

    with pytest.raises(FormatDetectionError):
        detect_format(path, None)


# ---------- CSV 读取 ----------


def test_csv_rows_map_by_header(write_csv):
    path = write_csv(
        ["id", "name", "category", "timestamp"],
        [["1", "Alice", "A", "2026-09-10T08:00:00Z"]],
    )

    items = list(read_csv(path, SCHEMA))

    assert items == [
        (2, {"id": "1", "name": "Alice", "category": "A", "timestamp": "2026-09-10T08:00:00Z"})
    ]


def test_csv_number_field_coerced(write_csv):
    path = write_csv(
        ["id", "name", "category", "score", "timestamp"],
        [
            ["1", "A", "A", "95", "2026-09-10T08:00:00Z"],
            ["2", "B", "B", "1.5", "2026-09-10T08:00:00Z"],
        ],
    )

    items = list(read_csv(path, SCHEMA))

    assert items[0][1]["score"] == 95
    assert isinstance(items[0][1]["score"], int)
    assert items[1][1]["score"] == 1.5


def test_csv_number_coercion_failure_keeps_string(write_csv):
    path = write_csv(
        ["id", "name", "category", "score", "timestamp"],
        [["1", "A", "A", "high", "2026-09-10T08:00:00Z"]],
    )

    items = list(read_csv(path, SCHEMA))

    # 保留原字符串, 由 validator 报 type_error
    assert items[0][1]["score"] == "high"


def test_csv_timestamp_and_unknown_fields_stay_strings(write_csv):
    path = write_csv(
        ["id", "name", "category", "timestamp", "note"],
        [["1", "A", "A", "1789027200", "hello"]],
    )

    items = list(read_csv(path, SCHEMA))

    assert items[0][1]["timestamp"] == "1789027200"
    assert items[0][1]["note"] == "hello"


def test_csv_empty_cell_optional_field_becomes_missing(write_csv):
    path = write_csv(
        ["id", "name", "category", "score", "timestamp"],
        [["1", "A", "A", "", "2026-09-10T08:00:00Z"]],
    )

    items = list(read_csv(path, SCHEMA))

    assert "score" not in items[0][1]


def test_csv_empty_cell_required_field_kept_as_empty_string(write_csv):
    path = write_csv(
        ["id", "name", "category", "timestamp"],
        [["1", "", "A", "2026-09-10T08:00:00Z"]],
    )

    items = list(read_csv(path, SCHEMA))

    assert items[0][1]["name"] == ""


def test_csv_column_count_mismatch_rejected(write_csv):
    path = write_csv(
        ["id", "name", "category", "timestamp"],
        [
            ["1", "A", "A", "2026-09-10T08:00:00Z"],
            "2,B,B",
            ["3", "C", "C", "2026-09-10T08:00:00Z"],
        ],
    )

    items = list(read_csv(path, SCHEMA))

    rejection = items[1]
    assert isinstance(rejection, Rejection)
    assert rejection.error_type == PARSE_ERROR
    assert "4" in rejection.reason and "3" in rejection.reason
    assert rejection.line == 3
    assert items[2][0] == 4  # 后续行继续处理


def test_csv_header_with_empty_column_name_raises(write_csv):
    path = write_csv(["id", "", "category"], [["1", "x", "A"]])

    with pytest.raises(ValueError):
        list(read_csv(path, SCHEMA))


def test_csv_header_with_duplicate_column_raises(write_csv):
    path = write_csv(["id", "id", "category"], [["1", "x", "A"]])

    with pytest.raises(ValueError):
        list(read_csv(path, SCHEMA))


def test_csv_only_header_yields_nothing(write_csv):
    path = write_csv(["id", "name", "category", "timestamp"])

    assert list(read_csv(path, SCHEMA)) == []


# ---------- 审查修复回归: 数字转换严格性与嗅探歧义 ----------


def test_csv_nan_inf_underscore_not_coerced(write_csv):
    path = write_csv(
        ["id", "name", "category", "score", "timestamp"],
        [
            ["1", "A", "A", "nan", "2026-09-10T08:00:00Z"],
            ["2", "B", "B", "inf", "2026-09-10T08:00:00Z"],
            ["3", "C", "C", "1_000", "2026-09-10T08:00:00Z"],
            ["4", "D", "A", "-1.5e3", "2026-09-10T08:00:00Z"],
        ],
    )

    items = list(read_csv(path, SCHEMA))

    # nan/inf/下划线保留原字符串(交给 validator 报 type_error); 科学计数法合法
    assert items[0][1]["score"] == "nan"
    assert items[1][1]["score"] == "inf"
    assert items[2][1]["score"] == "1_000"
    assert items[3][1]["score"] == -1500.0


def test_sniff_json_array_line_is_ambiguous(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("[1,2,3]\n", encoding="utf-8")

    with pytest.raises(FormatDetectionError):
        detect_format(path, None)


def test_csv_oversized_field_tolerated(write_csv, tmp_path):
    big = "x" * 200_000
    path = tmp_path / "big.csv"
    path.write_text(
        "id,name,category,timestamp\n"
        f'1,"{big}",A,2026-09-10T08:00:00Z\n',
        encoding="utf-8",
    )

    items = list(read_csv(path, SCHEMA))

    assert items[0][1]["name"] == big


def test_csv_column_mismatch_reject_preserves_quoting(write_csv):
    path = write_csv(
        ["id", "name", "category", "timestamp"],
        [["1", "Smith, John", "A"]],  # 3 列 vs 表头 4 列, 且值含逗号
    )

    items = list(read_csv(path, SCHEMA))

    rejection = items[0]
    assert isinstance(rejection, Rejection)
    # 原始引号形态保留, 不会被误读为 4 个值
    assert '"Smith, John"' in rejection.record


# ---------- BUG-002: UTF-8 BOM 剥离 ----------


def test_jsonl_with_bom_first_line_parses(tmp_path):
    path = tmp_path / "bom.jsonl"
    path.write_bytes('\ufeff{"id": "1"}\n{"id": "2"}\n'.encode("utf-8"))

    items = list(read_jsonl(path))

    assert items == [(1, {"id": "1"}), (2, {"id": "2"})]


def test_csv_with_bom_header_not_polluted(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes(
        "\ufeffid,name,category,timestamp\n1,Alice,A,2026-09-10T08:00:00Z\n".encode("utf-8")
    )

    items = list(read_csv(path, SCHEMA))

    assert items[0][1]["id"] == "1"  # 首列名必须是 id 而非 \ufeffid


def test_detect_format_tolerates_bom(tmp_path):
    path = tmp_path / "bom.txt"
    path.write_bytes('\ufeff{"id": "1"}\n'.encode("utf-8"))

    assert detect_format(path, None) == "jsonl"
