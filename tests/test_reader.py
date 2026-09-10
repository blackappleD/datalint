"""reader 模块单元测试: 逐行流式读取与 JSON 解析."""

from datalint.reader import read_jsonl
from datalint.schema import PARSE_ERROR, Rejection


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
