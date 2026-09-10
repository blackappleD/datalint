"""内置 schema 定义与共享类型: 字段规格, 错误类型常量, 剔除项."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Union

# 错误类型常量 (validator / cleaner / reporter 共用)
PARSE_ERROR = "parse_error"
MISSING_FIELD = "missing_field"
TYPE_ERROR = "type_error"
ENUM_ERROR = "enum_error"
TIMESTAMP_INVALID = "timestamp_invalid"
DUPLICATE = "duplicate"

ALL_ERROR_TYPES: tuple[str, ...] = (
    PARSE_ERROR,
    MISSING_FIELD,
    TYPE_ERROR,
    ENUM_ERROR,
    TIMESTAMP_INVALID,
    DUPLICATE,
)

# 字段类型标记
TYPE_STRING = "string"
TYPE_NUMBER = "number"
TYPE_TIMESTAMP = "timestamp"
TYPE_ENUM = "enum"


class _Missing:
    """去重时表示"字段缺失"的哨兵类型."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<MISSING>"


MISSING = _Missing()


@dataclass(frozen=True)
class FieldSpec:
    """schema 中单个字段的声明."""

    name: str
    type: str
    required: bool
    enum_values: frozenset[str] | None = None


# 内置 schema (集中定义于此处, 修改字段只需改这里)
SCHEMA: tuple[FieldSpec, ...] = (
    FieldSpec("id", TYPE_STRING, required=True),
    FieldSpec("name", TYPE_STRING, required=True),
    FieldSpec("category", TYPE_ENUM, required=True, enum_values=frozenset({"A", "B", "C"})),
    FieldSpec("score", TYPE_NUMBER, required=False),
    FieldSpec("timestamp", TYPE_TIMESTAMP, required=True),
)

SCHEMA_FIELD_NAMES: frozenset[str] = frozenset(spec.name for spec in SCHEMA)


@dataclass(frozen=True)
class Rejection:
    """一条被剔除记录的元信息.

    record 为原始记录 dict; 解析失败时为原始行文本 str.
    """

    line: int
    error_type: str
    reason: str
    record: Union[dict, str]

    def to_json_line(self) -> str:
        return json.dumps(
            {
                "line": self.line,
                "error_type": self.error_type,
                "reason": self.reason,
                "record": self.record,
            },
            ensure_ascii=False,
        )
