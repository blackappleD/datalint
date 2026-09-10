"""pytest 共享 fixture."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def write_jsonl(tmp_path):
    """构造临时 JSONL 输入文件.

    lines 中的元素可以是 dict(自动序列化)或 str(原样写入, 用于构造非法行).
    返回文件路径.
    """

    def _write(lines, name="input.jsonl"):
        path = tmp_path / name
        rendered = [
            line if isinstance(line, str) else json.dumps(line, ensure_ascii=False)
            for line in lines
        ]
        content = "\n".join(rendered)
        if rendered:
            content += "\n"
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def write_csv(tmp_path):
    """构造临时 CSV 输入文件.

    header 为列名列表(None 表示不写表头行); rows 中的元素可以是
    list(按列写入, 自动加引号转义)或 str(原样写入一行, 用于构造列数不匹配等非法行).
    返回文件路径.
    """

    def _write(header, rows=(), name="input.csv"):
        import csv as _csv
        import io

        buffer = io.StringIO()
        writer = _csv.writer(buffer, lineterminator="\n")
        if header is not None:
            writer.writerow(header)
        for row in rows:
            if isinstance(row, str):
                buffer.write(row + "\n")
            else:
                writer.writerow(row)
        path = tmp_path / name
        path.write_text(buffer.getvalue(), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def write_schema(tmp_path):
    """构造临时 schema JSON 文件.

    obj 为 dict(自动序列化)或 str(原样写入, 用于构造非法 JSON).
    返回文件路径.
    """

    def _write(obj, name="schema.json"):
        path = tmp_path / name
        content = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
        path.write_text(content, encoding="utf-8")
        return path

    return _write


def read_jsonl_file(path):
    """读取 JSONL 文件为记录列表(测试断言用)."""
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
