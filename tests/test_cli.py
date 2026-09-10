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


# ---------- v2 US1: 外部 schema ----------


CUSTOM_SCHEMA = {
    "fields": [
        {"name": "user_id", "type": "string", "required": True},
        {"name": "level", "type": "enum", "required": True, "enum_values": ["gold", "silver"]},
        {"name": "created_at", "type": "timestamp", "required": True},
    ]
}


def test_external_schema_replaces_builtin(write_jsonl, write_schema):
    schema_path = write_schema(CUSTOM_SCHEMA)
    # 记录符合自定义 schema, 但完全不含内置 schema 的必填字段(id/name/category/timestamp)
    path = write_jsonl(
        [
            {"user_id": "u1", "level": "gold", "created_at": "2026-09-10T08:00:00Z"},
            {"user_id": "u2", "level": "bronze", "created_at": "2026-09-10T08:00:00Z"},
        ]
    )

    code = run_cli([str(path), "--schema", str(schema_path)])

    assert code == 0
    clean = read_jsonl_file(path.parent / "input.clean.jsonl")
    assert [r["user_id"] for r in clean] == ["u1"]
    rejects = read_jsonl_file(path.parent / "input.rejects.jsonl")
    assert rejects[0]["error_type"] == "enum_error"
    assert "bronze" in rejects[0]["reason"]


def test_external_schema_timestamp_normalized(write_jsonl, write_schema):
    schema_path = write_schema(CUSTOM_SCHEMA)
    path = write_jsonl([{"user_id": "u1", "level": "gold", "created_at": "2026/09/10 08:00:00"}])

    run_cli([str(path), "--schema", str(schema_path)])

    clean = read_jsonl_file(path.parent / "input.clean.jsonl")
    assert clean[0]["created_at"] == "2026-09-10T08:00:00Z"


def test_dedup_by_validated_against_external_schema(write_jsonl, write_schema, capsys):
    schema_path = write_schema(CUSTOM_SCHEMA)
    path = write_jsonl(
        [
            {"user_id": "u1", "level": "gold", "created_at": "2026-09-10T08:00:00Z"},
            {"user_id": "u1", "level": "silver", "created_at": "2026-09-10T08:00:00Z"},
        ]
    )

    # user_id 在外部 schema 中合法(在内置 schema 中不存在)
    code = run_cli([str(path), "--schema", str(schema_path), "--dedup-by", "user_id"])
    assert code == 0
    assert len(read_jsonl_file(path.parent / "input.clean.jsonl")) == 1

    # id 在内置 schema 中合法, 但不在外部 schema 中 → 参数错误
    code = run_cli([str(path), "--schema", str(schema_path), "--dedup-by", "id"])
    assert code == 2


def test_invalid_schema_content_exits_2_without_outputs(write_jsonl, write_schema, capsys):
    schema_path = write_schema({"fields": [{"name": "a", "type": "datetime"}]})
    path = write_jsonl([valid_line()])

    code = run_cli([str(path), "--schema", str(schema_path)])

    assert code == 2
    err = capsys.readouterr().err
    assert "a" in err and "datetime" in err
    assert not (path.parent / "input.clean.jsonl").exists()
    assert not (path.parent / "input.rejects.jsonl").exists()


def test_invalid_schema_json_syntax_exits_2(write_jsonl, write_schema, capsys):
    schema_path = write_schema('{"fields": [')
    path = write_jsonl([valid_line()])

    code = run_cli([str(path), "--schema", str(schema_path)])

    assert code == 2
    assert "JSON" in capsys.readouterr().err


def test_missing_schema_file_exits_1(write_jsonl, tmp_path, capsys):
    path = write_jsonl([valid_line()])

    code = run_cli([str(path), "--schema", str(tmp_path / "nope.json")])

    assert code == 1
    assert not (path.parent / "input.clean.jsonl").exists()


def test_without_schema_option_builtin_applies(write_jsonl):
    path = write_jsonl([valid_line()])

    code = run_cli([str(path)])

    assert code == 0
    assert len(read_jsonl_file(path.parent / "input.clean.jsonl")) == 1


# ---------- v2 US2: CSV 输入与可选输出格式 ----------


def read_csv_file(path):
    import csv

    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_csv_input_auto_detected_by_extension(write_csv):
    path = write_csv(
        ["id", "name", "category", "timestamp"],
        [["1", "  Alice  ", "A", "2026/09/10 08:00:00"]],
    )

    code = run_cli([str(path)])

    assert code == 0
    clean = read_jsonl_file(path.parent / "input.csv.clean.jsonl")
    assert clean[0]["name"] == "Alice"
    assert clean[0]["timestamp"] == "2026-09-10T08:00:00Z"


def test_csv_in_csv_out(write_csv):
    path = write_csv(
        ["id", "name", "category", "score", "timestamp"],
        [["1", "Alice", "A", "95", "2026-09-10T08:00:00Z"]],
    )

    code = run_cli([str(path), "--output-format", "csv"])

    assert code == 0
    rows = read_csv_file(path.parent / "input.csv.clean.csv")
    assert rows[0]["id"] == "1"
    assert rows[0]["score"] == "95"
    assert rows[0]["timestamp"] == "2026-09-10T08:00:00Z"


def test_jsonl_and_csv_equivalent_inputs_same_report(write_jsonl, write_csv, capsys):
    records = [
        ("1", "Alice", "A", "2026-09-10T08:00:00Z"),
        ("2", "Bob", "X", "2026-09-10T08:00:00Z"),  # enum_error
        ("3", "Carol", "B", "bad-ts"),  # timestamp_invalid
    ]
    jsonl_path = write_jsonl(
        [
            {"id": i, "name": n, "category": c, "timestamp": t}
            for i, n, c, t in records
        ],
        name="a.jsonl",
    )
    csv_path = write_csv(
        ["id", "name", "category", "timestamp"],
        [list(r) for r in records],
        name="b.csv",
    )

    run_cli([str(jsonl_path), "--report-format", "json"])
    report_jsonl = json.loads(capsys.readouterr().out)
    run_cli([str(csv_path), "--report-format", "json"])
    report_csv = json.loads(capsys.readouterr().out)

    assert report_jsonl == report_csv
    assert report_jsonl["total"] == 3
    assert report_jsonl["passed"] == 1


def test_jsonl_and_csv_outputs_equivalent(write_jsonl, tmp_path):
    path = write_jsonl([valid_line("1", score=95)])

    run_cli([str(path), "-o", str(tmp_path / "out.jsonl")])
    run_cli([str(path), "--output-format", "csv", "-o", str(tmp_path / "out.csv")])

    jsonl_record = read_jsonl_file(tmp_path / "out.jsonl")[0]
    csv_record = read_csv_file(tmp_path / "out.csv")[0]
    assert set(jsonl_record) == set(csv_record)
    for key, value in jsonl_record.items():
        assert str(value) == csv_record[key]


def test_undetectable_format_exits_1_with_hint(tmp_path, capsys):
    path = tmp_path / "data.bin"
    path.write_text("plain words without structure\n", encoding="utf-8")

    code = run_cli([str(path)])

    assert code == 1
    assert "--input-format" in capsys.readouterr().err


def test_explicit_input_format_overrides_detection(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text(
        "id,name,category,timestamp\n1,Alice,A,2026-09-10T08:00:00Z\n", encoding="utf-8"
    )

    code = run_cli([str(path), "--input-format", "csv"])

    assert code == 0
    clean = read_jsonl_file(tmp_path / "data.txt.clean.jsonl")
    assert clean[0]["id"] == "1"


def test_csv_invalid_header_exits_1(write_csv, capsys):
    path = write_csv(["id", "id", "category"], [["1", "x", "A"]])

    code = run_cli([str(path)])

    assert code == 1
    assert "表头" in capsys.readouterr().err
    assert not (path.parent / "input.clean.jsonl").exists()


# ---------- v2 US3: --mask 脱敏 ----------


def test_mask_mixed_modes(write_jsonl):
    path = write_jsonl(
        [
            valid_line(
                "1",
                email="alice@example.com",
                phone="13800138000",
                home_phone="01088886666",
            )
        ]
    )

    code = run_cli([str(path), "--mask", "email:equal", "--mask", "phone:contain"])

    assert code == 0
    record = read_jsonl_file(path.parent / "input.clean.jsonl")[0]
    assert record["email"] == "a***************m"
    assert record["phone"] == "1*********0"
    assert record["home_phone"] == "0*********6"
    assert record["name"] == "Alice"  # 未命中字段原样


def test_mask_comma_merged_form_equivalent(write_jsonl):
    path = write_jsonl([valid_line("1", email="alice@example.com", phone="13800138000")])

    run_cli([str(path), "--mask", "email:equal,phone:contain"])

    record = read_jsonl_file(path.parent / "input.clean.jsonl")[0]
    assert record["email"] == "a***************m"
    assert record["phone"] == "1*********0"


def test_mask_original_value_absent_from_output(write_jsonl):
    secret = "alice@example.com"
    path = write_jsonl([valid_line("1", email=secret)])

    run_cli([str(path), "--mask", "email"])

    output_text = (path.parent / "input.clean.jsonl").read_text(encoding="utf-8")
    assert secret not in output_text


def test_dedup_by_masked_field_uses_real_value(write_jsonl):
    path = write_jsonl(
        [
            valid_line("1", name="alice@a.com"),
            valid_line("2", name="alice@b.com"),  # 掩码后同为 a*********m, 但真实值不同
        ]
    )

    code = run_cli([str(path), "--dedup-by", "name", "--mask", "name"])

    assert code == 0
    clean = read_jsonl_file(path.parent / "input.clean.jsonl")
    assert len(clean) == 2  # 真实值不同 → 不判重


def test_report_identical_with_and_without_mask(write_jsonl, write_csv, capsys):
    lines = [
        valid_line("1", email="a@x.com"),
        valid_line("1", email="b@y.com"),
        {"id": "3", "category": "A", "timestamp": "2026-09-10T08:00:00Z"},
    ]
    path = write_jsonl(lines)

    run_cli([str(path), "--dedup-by", "id", "--report-format", "json"])
    without_mask = json.loads(capsys.readouterr().out)
    run_cli([str(path), "--dedup-by", "id", "--report-format", "json", "--mask", "email"])
    with_mask = json.loads(capsys.readouterr().out)

    assert without_mask == with_mask


def test_mask_applies_to_csv_output(write_csv):
    path = write_csv(
        ["id", "name", "category", "timestamp", "email"],
        [["1", "Alice", "A", "2026-09-10T08:00:00Z", "alice@example.com"]],
    )

    run_cli([str(path), "--output-format", "csv", "--mask", "email"])

    rows = read_csv_file(path.parent / "input.csv.clean.csv")
    assert rows[0]["email"] == "a***************m"


def test_invalid_mask_mode_exits_2(write_jsonl, capsys):
    path = write_jsonl([valid_line()])

    code = run_cli([str(path), "--mask", "email:fuzzy"])

    assert code == 2
    assert "fuzzy" in capsys.readouterr().err


def test_empty_mask_pattern_exits_2(write_jsonl):
    path = write_jsonl([valid_line()])

    assert run_cli([str(path), "--mask", ","]) == 2
    assert run_cli([str(path), "--mask", ":equal"]) == 2


def test_rejects_file_keeps_original_values_by_design(write_jsonl):
    # 剔除明细面向人工回溯, 按设计保留未脱敏原值(README 已声明)
    path = write_jsonl(
        [
            valid_line("1", email="alice@example.com"),
            valid_line("1", email="bob@example.com"),  # duplicate
        ]
    )

    run_cli([str(path), "--dedup-by", "id", "--mask", "email"])

    clean = read_jsonl_file(path.parent / "input.clean.jsonl")
    assert clean[0]["email"] == "a***************m"
    rejects = read_jsonl_file(path.parent / "input.rejects.jsonl")
    assert rejects[0]["record"]["email"] == "bob@example.com"


# ---------- v2 US4: 不可解析行的持续处理 ----------


def test_csv_mixed_broken_rows_never_abort(write_csv, capsys):
    path = write_csv(
        ["id", "name", "category", "score", "timestamp"],
        [
            ["1", "Alice", "A", "95", "2026-09-10T08:00:00Z"],
            "2,Bob,B",  # 列数不匹配
            ["3", "Carol", "C", "not-a-number", "2026-09-10T08:00:00Z"],  # 类型转换失败
            ["4", "Dave", "Z", "80", "2026-09-10T08:00:00Z"],  # 枚举非法
            ["5", "Eve", "B", "70", "2026-09-10T08:00:00Z"],
        ],
    )

    code = run_cli([str(path), "--report-format", "json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 5
    assert payload["passed"] == 2
    assert payload["errors"]["parse_error"] == 1
    assert payload["errors"]["type_error"] == 1
    assert payload["errors"]["enum_error"] == 1
    rejects = read_jsonl_file(path.parent / "input.csv.rejects.jsonl")
    assert len(rejects) == 3
    for reject in rejects:
        assert isinstance(reject["line"], int)
        assert reject["reason"]


def test_csv_all_rows_broken_still_exits_0(write_csv, capsys):
    path = write_csv(
        ["id", "name", "category", "timestamp"],
        ["only,two", "a,b,c,d,e,f", "x"],
    )

    code = run_cli([str(path), "--report-format", "json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] == 0
    assert payload["rejected"] == 3
    assert read_jsonl_file(path.parent / "input.csv.clean.jsonl") == []
    assert len(read_jsonl_file(path.parent / "input.csv.rejects.jsonl")) == 3


def test_jsonl_broken_lines_regression(write_jsonl, capsys):
    path = write_jsonl([valid_line("1"), "not json at all", valid_line("2")])

    code = run_cli([str(path), "--report-format", "json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "total": 3,
        "passed": 2,
        "rejected": 1,
        "errors": {
            "parse_error": 1,
            "missing_field": 0,
            "type_error": 0,
            "enum_error": 0,
            "timestamp_invalid": 0,
            "duplicate": 0,
        },
    }


# ---------- Bugfix (BUG-001~006) 端到端 ----------


def test_e2e_subsecond_timestamps_not_dedup_killed(write_jsonl, capsys):
    path = write_jsonl(
        [
            valid_line("1", timestamp="2026-09-11T10:00:00.123Z"),
            valid_line("1", timestamp="2026-09-11T10:00:00.456Z"),
        ]
    )

    code = run_cli([str(path), "--dedup-by", "id,timestamp", "--report-format", "json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] == 2  # 不同时刻不得误判重复
    clean = read_jsonl_file(path.parent / "input.clean.jsonl")
    assert clean[0]["timestamp"] == "2026-09-11T10:00:00.123Z"
    assert clean[1]["timestamp"] == "2026-09-11T10:00:00.456Z"


def test_e2e_bom_jsonl_first_line_kept(tmp_path, capsys):
    path = tmp_path / "bom.jsonl"
    line = '{"id": "1", "name": "Alice", "category": "A", "timestamp": "2026-09-10T08:00:00Z"}'
    path.write_bytes(("\ufeff" + line + "\n").encode("utf-8"))

    code = run_cli([str(path), "--report-format", "json"])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["passed"] == 1


def test_e2e_bom_csv_not_rejected_wholesale(tmp_path, capsys):
    path = tmp_path / "bom.csv"
    path.write_bytes(
        "\ufeffid,name,category,timestamp\n1,Alice,A,2026-09-10T08:00:00Z\n".encode("utf-8")
    )

    code = run_cli([str(path), "--report-format", "json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] == 1
    assert payload["errors"]["missing_field"] == 0


def test_e2e_naive_timestamp_warning_on_stderr(write_jsonl, capsys):
    path = write_jsonl(
        [
            valid_line("1", timestamp="2026-09-11T10:00:00"),
            valid_line("2", timestamp="2026/09/11 10:00:00"),
            valid_line("3", timestamp="2026-09-11T10:00:00+08:00"),
        ]
    )

    code = run_cli([str(path), "--report-format", "json"])

    assert code == 0
    captured = capsys.readouterr()
    assert "2 条" in captured.err and "UTC" in captured.err
    assert json.loads(captured.out)["passed"] == 3  # 警告不影响统计与退出码


def test_e2e_no_warning_when_all_timestamps_zoned(write_jsonl, capsys):
    path = write_jsonl([valid_line("1", timestamp="2026-09-11T10:00:00Z")])

    run_cli([str(path)])

    assert "警告" not in capsys.readouterr().err


def test_e2e_same_stem_inputs_do_not_overwrite(write_jsonl, write_csv, capsys):
    jsonl_path = write_jsonl([valid_line("from-jsonl")], name="a.jsonl")
    csv_path = write_csv(
        ["id", "name", "category", "timestamp"],
        [["from-csv", "Bob", "B", "2026-09-10T08:00:00Z"]],
        name="a.csv",
    )

    run_cli([str(jsonl_path)])
    run_cli([str(csv_path)])

    jsonl_out = read_jsonl_file(jsonl_path.parent / "a.clean.jsonl")
    csv_out = read_jsonl_file(csv_path.parent / "a.csv.clean.jsonl")
    assert jsonl_out[0]["id"] == "from-jsonl"  # 未被 a.csv 的输出覆盖
    assert csv_out[0]["id"] == "from-csv"


def test_e2e_optional_null_preserved_in_output(write_jsonl, capsys):
    path = write_jsonl([valid_line("1", score=None)])

    code = run_cli([str(path), "--report-format", "json"])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["passed"] == 1
    clean = read_jsonl_file(path.parent / "input.clean.jsonl")
    assert clean[0]["score"] is None  # null 原样保留


def test_e2e_required_null_still_rejected(write_jsonl, capsys):
    path = write_jsonl([valid_line("1", name=None)])

    run_cli([str(path), "--report-format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"]["type_error"] == 1
