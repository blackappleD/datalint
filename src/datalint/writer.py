"""writer: 干净数据输出——JSONL 流式写出与 CSV 两遍法写出.

统一接口: write(record) / finalize() / abort().
两种 writer 都先写临时文件, finalize 时原子替换到目标路径, abort/失败不留残缺输出.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Union


def _cleanup(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


class JsonlWriter:
    """逐条流式写出 JSONL(临时文件 + 原子替换)."""

    def __init__(self, target: Union[str, Path]):
        self._target = Path(target)
        self._tmp = self._target.with_name(self._target.name + ".tmp")
        self._fh = open(self._tmp, "w", encoding="utf-8", newline="\n")

    def write(self, record: dict) -> None:
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def finalize(self) -> None:
        self._fh.close()
        os.replace(self._tmp, self._target)

    def abort(self) -> None:
        self._fh.close()
        _cleanup(self._tmp)


class CsvWriter:
    """两遍法写出 CSV.

    第一遍: 记录流式写入临时 JSONL, 同时按首见顺序累计列名并集;
    第二遍(finalize): 以列并集为表头将临时 JSONL 转写为临时 CSV,
    原子替换到目标路径并清理中间文件. 内存占用 O(列集合).
    """

    def __init__(self, target: Union[str, Path]):
        self._target = Path(target)
        self._stage = self._target.with_name(self._target.name + ".stage.jsonl.tmp")
        self._tmp = self._target.with_name(self._target.name + ".tmp")
        self._fh = open(self._stage, "w", encoding="utf-8", newline="\n")
        self._columns: dict[str, None] = {}  # 有序集合(首见顺序)

    def write(self, record: dict) -> None:
        for key in record:
            self._columns.setdefault(key)
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _cell(value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return json.dumps(value)
        return json.dumps(value, ensure_ascii=False)

    def finalize(self) -> None:
        self._fh.close()
        try:
            columns = list(self._columns)
            with (
                open(self._stage, encoding="utf-8") as stage_fh,
                open(self._tmp, "w", encoding="utf-8", newline="") as out_fh,
            ):
                if columns:
                    dict_writer = csv.DictWriter(
                        out_fh, fieldnames=columns, restval="", extrasaction="ignore"
                    )
                    dict_writer.writeheader()
                    for line in stage_fh:
                        record = json.loads(line)
                        dict_writer.writerow(
                            {key: self._cell(record.get(key)) for key in record}
                        )
            os.replace(self._tmp, self._target)
        finally:
            _cleanup(self._stage, self._tmp)

    def abort(self) -> None:
        self._fh.close()
        _cleanup(self._stage, self._tmp)