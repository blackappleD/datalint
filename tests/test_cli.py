"""CLI 端到端测试: 完整管道 + 退出码契约."""

import json

import pytest

from datalint import cli
from conftest import read_jsonl_file


def run_cli(args):
    """调用 main 并返回退出码."""
    with pytest.raises(SystemExit) as exc_info:
        cli.main(args)
    return exc_info.value.code


def valid_line(id_="1", name="Alice", category="A", timestamp="2026-09-10T08:00:00Z", **extra):
    record = {"id": id_, "name": name, "category": category, "timestamp": timestamp}
    record.update(extra)
    return record


# ---------- US1: 校验并剔除非法记录 ----------


def test_mixed_input_keeps_only_valid_records(write_jsonl, tmp_path):
    path = write_jsonl(
        [
            valid_line("1"),
            {"id": "2", "category": "A", "timestamp": "2026-09-10T08:00:00Z"},  # 缺 name
            valid_line("3", category="X"),  # 枚举非法
            "not valid json",
            valid_line("4"),
        ]
    )

    code = run_cli([str(path)])

    assert code == 0
    clean = read_jsonl_file(path.parent / "input.clean.jsonl")
    assert [r["id"] for r in clean] == ["1", "4"]
    rejects = read_jsonl_file(path.parent / "input.rejects.jsonl")
    assert len(rejects) == 3
    assert {r["error_type"] for r in rejects} == {"missing_field", "enum_error", "parse_error"}
    for r in rejects:
        assert isinstance(r["line"], int)
        assert r["reason"]
        assert "record" in r


def test_default_output_paths(write_jsonl):
    path = write_jsonl([valid_line()], name="data.jsonl")

    run_cli([str(path)])

    assert (path.parent / "data.clean.jsonl").is_file()
    assert (path.parent / "data.rejects.jsonl").is_file()


def test_explicit_output_paths(write_jsonl, tmp_path):
    path = write_jsonl([valid_line()])
    out = tmp_path / "out" / "clean.jsonl"
    rej = tmp_path / "out" / "bad.jsonl"
    out.parent.mkdir()

    code = run_cli([str(path), "-o", str(out), "--rejects", str(rej)])

    assert code == 0
    assert len(read_jsonl_file(out)) == 1
    assert read_jsonl_file(rej) == []


def test_missing_input_file_exits_1(tmp_path, capsys):
    missing = tmp_path / "nope.jsonl"

    code = run_cli([str(missing)])

    assert code == 1
    assert str(missing) in capsys.readouterr().err
    assert not (tmp_path / "nope.clean.jsonl").exists()


def test_rejects_file_preserves_original_record(write_jsonl):
    path = write_jsonl([{"id": "2", "category": "A", "timestamp": "2026-09-10T08:00:00Z"}])

    run_cli([str(path)])

    rejects = read_jsonl_file(path.parent / "input.rejects.jsonl")
    assert rejects[0]["record"]["id"] == "2"
    assert rejects[0]["line"] == 1


# ---------- US2: 清洗合法记录 ----------


def test_output_is_cleaned_and_normalized(write_jsonl):
    path = write_jsonl(
        [
            valid_line("1", name="  Alice  ", timestamp="2026/09/10 08:00:00"),
            valid_line("2", timestamp=1789027200),
        ]
    )

    code = run_cli([str(path)])

    assert code == 0
    clean = read_jsonl_file(path.parent / "input.clean.jsonl")
    assert clean[0]["name"] == "Alice"
    assert clean[0]["timestamp"] == "2026-09-10T08:00:00Z"
    assert clean[1]["timestamp"] == "2026-09-10T08:00:00Z"


def test_bad_timestamp_is_rejected(write_jsonl):
    path = write_jsonl([valid_line("1", timestamp="昨天下午")])

    run_cli([str(path)])

    assert read_jsonl_file(path.parent / "input.clean.jsonl") == []
    rejects = read_jsonl_file(path.parent / "input.rejects.jsonl")
    assert rejects[0]["error_type"] == "timestamp_invalid"


def test_dedup_by_keeps_first_occurrence(write_jsonl):
    path = write_jsonl(
        [
            valid_line("1", name="Alice"),
            valid_line("1", name="Bob"),
            valid_line("2"),
        ]
    )

    code = run_cli([str(path), "--dedup-by", "id"])

    assert code == 0
    clean = read_jsonl_file(path.parent / "input.clean.jsonl")
    assert [r["id"] for r in clean] == ["1", "2"]
    assert clean[0]["name"] == "Alice"
    rejects = read_jsonl_file(path.parent / "input.rejects.jsonl")
    assert rejects[0]["error_type"] == "duplicate"
    assert rejects[0]["line"] == 2


def test_no_dedup_without_flag(write_jsonl):
    path = write_jsonl([valid_line("1"), valid_line("1")])

    run_cli([str(path)])

    assert len(read_jsonl_file(path.parent / "input.clean.jsonl")) == 2


def test_dedup_by_unknown_field_exits_2(write_jsonl, capsys):
    path = write_jsonl([valid_line()])

    code = run_cli([str(path), "--dedup-by", "nonfield"])

    assert code == 2
    assert "nonfield" in capsys.readouterr().err


# ---------- US3: 生成质检报告 ----------


def mixed_input(write_jsonl):
    return write_jsonl(
        [
            valid_line("1"),
            valid_line("1"),  # duplicate (with --dedup-by id)
            {"id": "2", "category": "A", "timestamp": "2026-09-10T08:00:00Z"},  # 缺 name
            "not json",
            valid_line("3", timestamp="???"),
        ]
    )


def test_json_report_structure_and_numbers(write_jsonl, capsys):
    path = mixed_input(write_jsonl)

    code = run_cli([str(path), "--dedup-by", "id", "--report-format", "json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 5
    assert payload["passed"] == 1
    assert payload["rejected"] == 4
    assert payload["errors"]["duplicate"] == 1
    assert payload["errors"]["missing_field"] == 1
    assert payload["errors"]["parse_error"] == 1
    assert payload["errors"]["timestamp_invalid"] == 1
    assert payload["errors"]["enum_error"] == 0


def test_table_and_json_reports_agree(write_jsonl, capsys):
    path = mixed_input(write_jsonl)

    run_cli([str(path), "--dedup-by", "id", "--report-format", "json"])
    payload = json.loads(capsys.readouterr().out)

    run_cli([str(path), "--dedup-by", "id", "--report-format", "table"])
    table = capsys.readouterr().out

    for key in ("total", "passed", "rejected"):
        row = next(l for l in table.splitlines() if l.startswith(key))
        assert row.split()[-1] == str(payload[key])
    for error_type, count in payload["errors"].items():
        row = next(l for l in table.splitlines() if l.startswith(error_type))
        assert row.split()[-1] == str(count)


def test_report_invariant_holds(write_jsonl, capsys):
    path = mixed_input(write_jsonl)

    run_cli([str(path), "--report-format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["total"] == payload["passed"] + payload["rejected"]
    assert payload["rejected"] == sum(payload["errors"].values())


def test_report_file_writes_to_disk(write_jsonl, tmp_path, capsys):
    path = write_jsonl([valid_line()])
    report_path = tmp_path / "report.json"

    code = run_cli([str(path), "--report-format", "json", "--report-file", str(report_path)])

    assert code == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["passed"] == 1
    assert capsys.readouterr().out == ""


def test_default_report_is_table_on_stdout(write_jsonl, capsys):
    path = write_jsonl([valid_line()])

    run_cli([str(path)])

    out = capsys.readouterr().out
    assert "datalint report" in out
    assert "passed" in out


# ---------- 边界情况 ----------


def test_empty_input_file_completes_normally(write_jsonl, capsys):
    path = write_jsonl([])

    code = run_cli([str(path), "--report-format", "json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 0
    assert read_jsonl_file(path.parent / "input.clean.jsonl") == []
    assert read_jsonl_file(path.parent / "input.rejects.jsonl") == []


def test_all_invalid_records_still_exit_0(write_jsonl, capsys):
    path = write_jsonl(["not json", "also not json"])

    code = run_cli([str(path), "--report-format", "json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "total": 2,
        "passed": 0,
        "rejected": 2,
        "errors": {
            "parse_error": 2,
            "missing_field": 0,
            "type_error": 0,
            "enum_error": 0,
            "timestamp_invalid": 0,
            "duplicate": 0,
        },
    }
    assert read_jsonl_file(path.parent / "input.clean.jsonl") == []


def test_blank_lines_not_counted_in_total(write_jsonl, capsys):
    path = write_jsonl([valid_line("1"), "", "   ", valid_line("2")])

    run_cli([str(path), "--report-format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 2
    assert payload["passed"] == 2


def test_python_m_datalint_is_equivalent(write_jsonl):
    import subprocess
    import sys

    path = write_jsonl([valid_line()])

    result = subprocess.run(
        [sys.executable, "-m", "datalint", str(path), "--report-format", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] == 1
    assert len(read_jsonl_file(path.parent / "input.clean.jsonl")) == 1


# ---------- 路径冲突与损坏输入防护 ----------


def test_output_same_as_input_exits_2_and_preserves_input(write_jsonl, capsys):
    path = write_jsonl([valid_line()])
    original = path.read_text(encoding="utf-8")

    code = run_cli([str(path), "-o", str(path)])

    assert code == 2
    assert capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == original


def test_rejects_same_as_input_exits_2_and_preserves_input(write_jsonl):
    path = write_jsonl([valid_line()])
    original = path.read_text(encoding="utf-8")

    code = run_cli([str(path), "--rejects", str(path)])

    assert code == 2
    assert path.read_text(encoding="utf-8") == original


def test_output_same_as_rejects_exits_2(write_jsonl, tmp_path):
    path = write_jsonl([valid_line()])
    target = tmp_path / "same.jsonl"

    code = run_cli([str(path), "-o", str(target), "--rejects", str(target)])

    assert code == 2
    assert not target.exists()


def test_non_utf8_input_exits_1_without_stray_outputs(tmp_path, capsys):
    path = tmp_path / "bad.jsonl"
    path.write_bytes(b'{"id": "1"}\n\xff\xfe broken \n')

    code = run_cli([str(path)])

    assert code == 1
    err = capsys.readouterr().err
    assert "错误" in err
    assert "Traceback" not in err
    assert not (tmp_path / "bad.clean.jsonl").exists()
    assert not (tmp_path / "bad.rejects.jsonl").exists()


def test_all_empty_dedup_tokens_exit_2(write_jsonl, capsys):
    path = write_jsonl([valid_line()])

    code = run_cli([str(path), "--dedup-by", ","])

    assert code == 2
