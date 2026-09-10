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


def read_jsonl_file(path):
    """读取 JSONL 文件为记录列表(测试断言用)."""
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
