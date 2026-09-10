"""reader: 输入格式识别与 JSONL/CSV 流式读取."""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Optional, Union

from datalint.schema import (
    PARSE_ERROR,
    TYPE_NUMBER,
    FieldSpec,
    Rejection,
)

ReaderItem = Union[tuple[int, dict], Rejection]

_EXTENSION_FORMATS = {".csv": "csv", ".jsonl": "jsonl", ".json": "jsonl"}
# 严格数字文本: 拒绝 nan/inf/下划线分组等 float() 额外接受的形态
_STRICT_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")

# 超长字段是合法数据, 放宽 csv 模块默认 128KB 字段上限
csv.field_size_limit(sys.maxsize)


class FormatDetectionError(ValueError):
    """无法识别输入文件格式."""


def detect_format(path: Union[str, Path], explicit: Optional[str]) -> str:
    """确定输入格式: 显式指定 > 扩展名 > 首个非空行嗅探.

    无法判断时抛 FormatDetectionError(提示显式指定).
    """
    if explicit is not None:
        return explicit
    suffix = Path(path).suffix.lower()
    if suffix in _EXTENSION_FORMATS:
        return _EXTENSION_FORMATS[suffix]

    first_line = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                first_line = line.strip()
                break
    if first_line is not None:
        try:
            parsed = json.loads(first_line)
        except json.JSONDecodeError:
            if "," in first_line and all(
                cell.strip() for cell in next(csv.reader([first_line]))
            ):
                return "csv"
        else:
            if isinstance(parsed, dict):
                return "jsonl"
            # 首行是合法 JSON 但不是对象(如数组/标量): 既非合法 JSONL 记录,
            # 又极易被 CSV 启发误判 → 视为无法识别
    raise FormatDetectionError(
        f"无法识别输入文件格式: {path} (请使用 --input-format 显式指定 jsonl 或 csv)"
    )


def read_jsonl(path: Union[str, Path]) -> Iterator[ReaderItem]:
    """逐行读取 JSONL 文件, 惰性产出 (行号, 记录) 或 Rejection.

    - 行号从 1 起, 按物理行计
    - 空白行直接跳过, 不计数
    - 解析失败或 JSON 值不是对象时产出 Rejection(parse_error), record 为原始行文本
    """
    with open(path, encoding="utf-8") as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            text = raw_line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                yield Rejection(line_no, PARSE_ERROR, f"JSON 解析失败: {exc.msg}", text)
                continue
            if not isinstance(parsed, dict):
                yield Rejection(
                    line_no, PARSE_ERROR, "JSON 值不是对象(每行必须是一个 JSON object)", text
                )
                continue
            yield line_no, parsed


def _coerce_number(text: str):
    if not _STRICT_NUMBER.match(text):
        return text  # 保留原字符串, 由 validator 报 type_error
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def _validate_header(header: list[str], path) -> None:
    if any(not name.strip() for name in header):
        raise ValueError(f"CSV 表头含空列名: {path}")
    if len(set(header)) != len(header):
        raise ValueError(f"CSV 表头含重复列名: {path}")


def _reserialize_row(row: list[str]) -> str:
    """将解析后的行按 CSV 语义重新序列化, 保留含逗号/引号值的原始形态."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="").writerow(row)
    return buffer.getvalue()


def read_csv(path: Union[str, Path], schema: tuple[FieldSpec, ...]) -> Iterator[ReaderItem]:
    """逐行读取带表头的 CSV 文件, 产出 (行号, 记录) 或 Rejection.

    - 表头行定义字段名; 空列名/重复列名抛 ValueError(运行错误)
    - 行号按物理行位置计(csv.reader.line_num)
    - 列数与表头不符产出 Rejection(parse_error), record 为该行原文
    - number 字段按 schema 转换(int 优先 float 兜底), 失败保留原字符串
    - 空单元格: 可选字段视为缺失; 必填字段保留空字符串
    """
    required_names = {spec.name for spec in schema if spec.required}
    number_names = {spec.name for spec in schema if spec.type == TYPE_NUMBER}

    with open(path, encoding="utf-8", newline="") as fh:
        rows = csv.reader(fh)
        header: Optional[list[str]] = None
        for row in rows:
            if not row or all(not cell.strip() for cell in row):
                continue
            if header is None:
                header = row
                _validate_header(header, path)
                continue
            line_no = rows.line_num
            if len(row) != len(header):
                yield Rejection(
                    line_no,
                    PARSE_ERROR,
                    f"列数不匹配: 期望 {len(header)} 列, 实际 {len(row)} 列",
                    _reserialize_row(row),
                )
                continue
            record: dict = {}
            for name, cell in zip(header, row):
                if cell == "" and name not in required_names:
                    continue
                record[name] = _coerce_number(cell) if name in number_names and cell else cell
            yield line_no, record
