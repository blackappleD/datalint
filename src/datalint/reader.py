"""reader: 逐行流式读取 JSONL 并解析为记录."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Union

from datalint.schema import PARSE_ERROR, Rejection

ReaderItem = Union[tuple[int, dict], Rejection]


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
