"""cli: 参数解析与管道编排 (格式识别 → reader → validator → cleaner → dedup → mask → writer)."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Optional

from datalint.cleaner import Deduplicator, clean
from datalint.masker import MaskRule, apply_mask, parse_mask_rules
from datalint.reader import FormatDetectionError, detect_format, read_csv, read_jsonl
from datalint.reporter import Report, render_json, render_table
from datalint.schema import (
    SCHEMA,
    FieldSpec,
    Rejection,
    SchemaValidationError,
    field_names,
    load_schema,
)
from datalint.validator import validate
from datalint.writer import CsvWriter, JsonlWriter

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datalint",
        description="清洗和质检结构化数据集(JSONL/CSV): schema 校验、清洗、去重、脱敏、质检报告.",
    )
    parser.add_argument("input", help="输入文件路径(JSONL 或 CSV)")
    parser.add_argument(
        "-o", "--output", help="干净数据输出路径(默认: <输入名>.clean.<输出格式>)"
    )
    parser.add_argument(
        "--rejects", help="剔除明细输出路径(默认: <输入名>.rejects.jsonl)"
    )
    parser.add_argument(
        "--dedup-by",
        help="逗号分隔的去重字段(必须是生效 schema 中定义的字段); 未指定则不去重",
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
    parser.add_argument(
        "--schema",
        help="外部 schema JSON 文件路径; 指定后完全替代内置 schema",
    )
    parser.add_argument(
        "--input-format",
        choices=("jsonl", "csv"),
        help="显式指定输入格式, 跳过自动识别(缺省: 扩展名优先+内容嗅探)",
    )
    parser.add_argument(
        "--output-format",
        choices=("jsonl", "csv"),
        default="jsonl",
        help="干净数据输出格式(默认: jsonl)",
    )
    parser.add_argument(
        "--mask",
        action="append",
        metavar="PATTERN[:MODE][,...]",
        help="脱敏字段模式(可重复); MODE 为 equal(默认, 精确)或 contain(模糊, 不区分大小写)",
    )
    return parser


def _default_path(input_path: Path, suffix: str) -> Path:
    return input_path.with_name(input_path.stem + suffix)


def _parse_dedup_fields(
    raw: Optional[str],
    parser: argparse.ArgumentParser,
    schema: tuple[FieldSpec, ...],
) -> tuple[str, ...]:
    """解析并校验 --dedup-by; 非法时经 parser.error 以退出码 2 终止."""
    if raw is None:
        return ()
    fields = tuple(field.strip() for field in raw.split(",") if field.strip())
    if not fields:
        parser.error(f"--dedup-by 未包含任何有效字段: {raw!r}")
    allowed = field_names(schema)
    for field in fields:
        if field not in allowed:
            parser.error(f"--dedup-by 字段不在 schema 中: {field}")
    return fields


def _process(
    item, dedup: Deduplicator, schema: tuple[FieldSpec, ...]
) -> tuple[Optional[dict], Optional[Rejection]]:
    """将 reader 产出的一项处理为 (干净记录, None) 或 (None, Rejection)."""
    if isinstance(item, Rejection):
        return None, item
    line_no, record = item
    rejection = validate(line_no, record, schema)
    if rejection is not None:
        return None, rejection
    cleaned = clean(line_no, record, schema)
    if isinstance(cleaned, Rejection):
        return None, cleaned
    rejection = dedup.check(line_no, cleaned)
    if rejection is not None:
        return None, rejection
    return cleaned, None


def run(
    args: argparse.Namespace,
    dedup_fields: tuple[str, ...],
    schema: tuple[FieldSpec, ...],
    mask_rules: tuple[MaskRule, ...] = (),
) -> int:
    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"错误: 输入文件不存在或不可读: {input_path}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    try:
        input_format = detect_format(input_path, args.input_format)
    except FormatDetectionError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    except UnicodeDecodeError as exc:
        print(f"错误: 输入文件不是合法 UTF-8: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    output_suffix = ".clean.csv" if args.output_format == "csv" else ".clean.jsonl"
    output_path = Path(args.output) if args.output else _default_path(input_path, output_suffix)
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
    rejects_tmp = rejects_path.with_name(rejects_path.name + ".tmp")

    # writer 内部走临时文件 + 原子替换, 任何失败不留残缺输出
    writer_cls = CsvWriter if args.output_format == "csv" else JsonlWriter
    writer = writer_cls(output_path)
    try:
        with open(rejects_tmp, "w", encoding="utf-8") as rejects_fh:
            items = (
                read_csv(input_path, schema)
                if input_format == "csv"
                else read_jsonl(input_path)
            )
            for item in items:
                record, rejection = _process(item, dedup, schema)
                if rejection is not None:
                    rejects_fh.write(rejection.to_json_line() + "\n")
                    report.count_reject(rejection.error_type)
                else:
                    # 脱敏在 dedup 之后应用: 只影响输出, 不影响质检语义
                    writer.write(apply_mask(record, mask_rules))
                    report.count_pass()
        writer.finalize()
        try:
            os.replace(rejects_tmp, rejects_path)
        except OSError:
            # 干净输出已提交但明细提交失败: 回收干净输出, 维持"全有或全无"
            _cleanup(output_path)
            raise
    except UnicodeDecodeError as exc:
        writer.abort()
        _cleanup(rejects_tmp)
        print(f"错误: 输入文件不是合法 UTF-8: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    except csv.Error as exc:
        # csv.Error 直接继承 Exception, 不在 ValueError/OSError 链中
        writer.abort()
        _cleanup(rejects_tmp)
        print(f"错误: CSV 解析失败: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    except ValueError as exc:  # CSV 表头非法等
        writer.abort()
        _cleanup(rejects_tmp)
        print(f"错误: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    except OSError as exc:
        writer.abort()
        _cleanup(rejects_tmp)
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


def _cleanup(*paths: Path) -> None:
    """删除失败时遗留的临时文件(尽力而为)."""
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _resolve_schema(raw_path: Optional[str]) -> tuple[FieldSpec, ...]:
    """确定生效 schema: --schema 加载成功值或内置默认.

    schema 内容非法 → SystemExit(2); 文件不可读 → SystemExit(1).
    """
    if raw_path is None:
        return SCHEMA
    try:
        return load_schema(raw_path)
    except SchemaValidationError as exc:
        print(f"错误: schema 文件非法: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE_ERROR)
    except OSError as exc:
        print(f"错误: schema 文件不可读: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_RUNTIME_ERROR)


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    schema = _resolve_schema(args.schema)
    dedup_fields = _parse_dedup_fields(args.dedup_by, parser, schema)
    try:
        mask_rules = parse_mask_rules(args.mask)
    except ValueError as exc:
        parser.error(str(exc))
    sys.exit(run(args, dedup_fields, schema, mask_rules))
