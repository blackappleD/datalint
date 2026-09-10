"""cli: 参数解析与管道编排 (reader → validator → cleaner → dedup → 输出)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from datalint.cleaner import Deduplicator, clean
from datalint.reader import read_jsonl
from datalint.reporter import Report, render_json, render_table
from datalint.schema import SCHEMA_FIELD_NAMES, Rejection
from datalint.validator import validate

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datalint",
        description="清洗和质检结构化 JSONL 数据集: schema 校验、清洗、去重、质检报告.",
    )
    parser.add_argument("input", help="输入 JSONL 文件路径")
    parser.add_argument(
        "-o", "--output", help="干净数据输出路径(默认: <输入名>.clean.jsonl)"
    )
    parser.add_argument(
        "--rejects", help="剔除明细输出路径(默认: <输入名>.rejects.jsonl)"
    )
    parser.add_argument(
        "--dedup-by",
        help="逗号分隔的去重字段(必须是 schema 中定义的字段); 未指定则不去重",
    )
    parser.add_argument(
        "--report-format",
        choices=("table", "json"),
        default="table",
        help="质检报告格式(默认: table)",
    )
    parser.add_argument(
        "--report-file", help="报告写入文件而非标准输出"
    )
    return parser


def _default_path(input_path: Path, suffix: str) -> Path:
    return input_path.with_name(input_path.stem + suffix)


def _cleanup(*paths: Path) -> None:
    """删除失败时遗留的临时文件(尽力而为)."""
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _parse_dedup_fields(raw: Optional[str], parser: argparse.ArgumentParser) -> tuple[str, ...]:
    """解析并校验 --dedup-by; 非法时经 parser.error 以退出码 2 终止."""
    if raw is None:
        return ()
    fields = tuple(field.strip() for field in raw.split(",") if field.strip())
    if not fields:
        parser.error(f"--dedup-by 未包含任何有效字段: {raw!r}")
    for field in fields:
        if field not in SCHEMA_FIELD_NAMES:
            parser.error(f"--dedup-by 字段不在 schema 中: {field}")
    return fields


def _process(item, dedup: Deduplicator) -> tuple[Optional[dict], Optional[Rejection]]:
    """将 reader 产出的一项处理为 (干净记录, None) 或 (None, Rejection)."""
    if isinstance(item, Rejection):
        return None, item
    line_no, record = item
    rejection = validate(line_no, record)
    if rejection is not None:
        return None, rejection
    cleaned = clean(line_no, record)
    if isinstance(cleaned, Rejection):
        return None, cleaned
    rejection = dedup.check(line_no, cleaned)
    if rejection is not None:
        return None, rejection
    return cleaned, None


def run(args: argparse.Namespace, dedup_fields: tuple[str, ...]) -> int:
    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"错误: 输入文件不存在或不可读: {input_path}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    output_path = Path(args.output) if args.output else _default_path(input_path, ".clean.jsonl")
    rejects_path = Path(args.rejects) if args.rejects else _default_path(input_path, ".rejects.jsonl")

    # 输入/输出/明细三个路径必须互不相同, 否则先行截断会静默清空数据
    resolved = [input_path.resolve(), output_path.resolve(), rejects_path.resolve()]
    if len(set(resolved)) != 3:
        print(
            f"错误: 输入、输出、剔除明细路径不能相同: "
            f"input={input_path}, output={output_path}, rejects={rejects_path}",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR

    dedup = Deduplicator(dedup_fields)
    report = Report()

    # 先写临时文件, 全部成功后原子替换到最终路径, 失败不留残缺输出
    output_tmp = output_path.with_name(output_path.name + ".tmp")
    rejects_tmp = rejects_path.with_name(rejects_path.name + ".tmp")
    try:
        with (
            open(output_tmp, "w", encoding="utf-8") as out_fh,
            open(rejects_tmp, "w", encoding="utf-8") as rejects_fh,
        ):
            for item in read_jsonl(input_path):
                record, rejection = _process(item, dedup)
                if rejection is not None:
                    rejects_fh.write(rejection.to_json_line() + "\n")
                    report.count_reject(rejection.error_type)
                else:
                    out_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    report.count_pass()
        os.replace(output_tmp, output_path)
        os.replace(rejects_tmp, rejects_path)
    except UnicodeDecodeError as exc:
        _cleanup(output_tmp, rejects_tmp)
        print(f"错误: 输入文件不是合法 UTF-8: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    except OSError as exc:
        _cleanup(output_tmp, rejects_tmp)
        print(f"错误: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    rendered = render_json(report) if args.report_format == "json" else render_table(report)
    try:
        if args.report_file:
            Path(args.report_file).write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
    except OSError as exc:
        print(f"错误: 报告写入失败: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    return EXIT_OK


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    dedup_fields = _parse_dedup_fields(args.dedup_by, parser)
    sys.exit(run(args, dedup_fields))
