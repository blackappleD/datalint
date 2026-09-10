"""writer 模块单元测试: JSONL 流式写出与 CSV 两遍法写出."""

import csv
import json

from datalint.writer import CsvWriter, JsonlWriter


def write_all(writer, records):
    for record in records:
        writer.write(record)
    writer.finalize()


def no_tmp_leftovers(directory):
    return not any(p.name.endswith(".tmp") for p in directory.iterdir())


# ---------- JsonlWriter ----------


def test_jsonl_writer_writes_records(tmp_path):
    target = tmp_path / "out.jsonl"

    write_all(JsonlWriter(target), [{"a": 1}, {"b": "中文"}])

    lines = target.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": "中文"}
    assert no_tmp_leftovers(tmp_path)


def test_jsonl_writer_abort_leaves_nothing(tmp_path):
    target = tmp_path / "out.jsonl"
    writer = JsonlWriter(target)
    writer.write({"a": 1})

    writer.abort()

    assert not target.exists()
    assert no_tmp_leftovers(tmp_path)


# ---------- CsvWriter ----------


def read_csv_file(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def test_csv_writer_produces_header_and_rows(tmp_path):
    target = tmp_path / "out.csv"

    write_all(CsvWriter(target), [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}])

    rows = read_csv_file(target)
    assert rows[0] == ["id", "name"]
    assert rows[1] == ["1", "Alice"]
    assert rows[2] == ["2", "Bob"]
    assert no_tmp_leftovers(tmp_path)


def test_csv_writer_column_union_first_seen_order(tmp_path):
    target = tmp_path / "out.csv"

    write_all(
        CsvWriter(target),
        [
            {"id": "1", "name": "Alice"},
            {"id": "2", "extra": "x"},  # 新字段追加列尾
        ],
    )

    rows = read_csv_file(target)
    assert rows[0] == ["id", "name", "extra"]
    assert rows[1] == ["1", "Alice", ""]  # 缺列输出空
    assert rows[2] == ["2", "", "x"]


def test_csv_writer_serializes_scalars(tmp_path):
    target = tmp_path / "out.csv"

    write_all(CsvWriter(target), [{"n": 95, "f": 1.5, "none": None, "s": "x"}])

    rows = read_csv_file(target)
    assert rows[1] == ["95", "1.5", "", "x"]


def test_csv_writer_escapes_commas_and_quotes(tmp_path):
    target = tmp_path / "out.csv"

    write_all(CsvWriter(target), [{"a": 'he said "hi"', "b": "1,2"}])

    rows = read_csv_file(target)
    assert rows[1] == ['he said "hi"', "1,2"]


def test_csv_writer_abort_cleans_all_temps(tmp_path):
    target = tmp_path / "out.csv"
    writer = CsvWriter(target)
    writer.write({"a": 1})

    writer.abort()

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_csv_writer_empty_stream_produces_empty_file(tmp_path):
    target = tmp_path / "out.csv"

    write_all(CsvWriter(target), [])

    assert target.exists()
    assert target.read_text(encoding="utf-8") == ""
    assert no_tmp_leftovers(tmp_path)
