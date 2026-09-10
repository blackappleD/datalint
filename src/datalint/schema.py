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


def field_names(schema: tuple[FieldSpec, ...]) -> frozenset[str]:
    """返回 schema 声明的全部字段名集合."""
    return frozenset(spec.name for spec in schema)


def timestamp_fields(schema: tuple[FieldSpec, ...]) -> tuple[str, ...]:
    """返回 schema 中时间戳类型字段名(按声明顺序)."""
    return tuple(spec.name for spec in schema if spec.type == TYPE_TIMESTAMP)


_SUPPORTED_TYPES = (TYPE_STRING, TYPE_NUMBER, TYPE_TIMESTAMP, TYPE_ENUM)


class SchemaValidationError(ValueError):
    """外部 schema 文件结构或内容非法."""


def _validate_field_entry(index: int, entry: object, seen_names: set[str]) -> FieldSpec:
    """校验 fields 数组中的单个元素, 返回 FieldSpec; 非法时抛 SchemaValidationError."""
    where = f"fields[{index}]"
    if not isinstance(entry, dict):
        raise SchemaValidationError(f"{where} 必须是对象, 实际为 {type(entry).__name__}")

    name = entry.get("name")
    if not isinstance(name, str) or not name:
        raise SchemaValidationError(f"{where} 的 name 必须是非空字符串, 实际为 {name!r}")
    if name in seen_names:
        raise SchemaValidationError(f"字段名重复: {name!r}")

    field_type = entry.get("type")
    if field_type not in _SUPPORTED_TYPES:
        supported = ", ".join(_SUPPORTED_TYPES)
        raise SchemaValidationError(
            f"字段 {name!r} 的 type 非法: {field_type!r} (支持的类型: {supported})"
        )

    required = entry.get("required", False)
    if not isinstance(required, bool):
        raise SchemaValidationError(
            f"字段 {name!r} 的 required 必须是布尔值, 实际为 {required!r}"
        )

    enum_values = entry.get("enum_values")
    if field_type == TYPE_ENUM:
        if (
            not isinstance(enum_values, list)
            or not enum_values
            or not all(isinstance(v, str) for v in enum_values)
        ):
            raise SchemaValidationError(
                f"枚举字段 {name!r} 的 enum_values 必须是非空字符串数组, 实际为 {enum_values!r}"
            )
        frozen_values: frozenset[str] | None = frozenset(enum_values)
    else:
        if enum_values is not None:
            raise SchemaValidationError(
                f"非枚举字段 {name!r} 不得携带 enum_values"
            )
        frozen_values = None

    return FieldSpec(name, field_type, required=required, enum_values=frozen_values)


def load_schema(path) -> tuple[FieldSpec, ...]:
    """从外部 JSON 文件加载 schema, 校验通过后返回与内置 SCHEMA 同型的元组.

    结构/内容非法抛 SchemaValidationError(参数错误);
    文件不存在或不可读抛 OSError(运行错误).
    """
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"schema 文件 JSON 解析失败: {exc.msg} (行 {exc.lineno})") from exc

    if not isinstance(document, dict):
        raise SchemaValidationError("schema 文件顶层必须是 JSON 对象")
    fields = document.get("fields")
    if not isinstance(fields, list) or not fields:
        raise SchemaValidationError("schema 文件必须包含非空的 fields 数组")

    specs: list[FieldSpec] = []
    seen_names: set[str] = set()
    for index, entry in enumerate(fields):
        spec = _validate_field_entry(index, entry, seen_names)
        seen_names.add(spec.name)
        specs.append(spec)
    return tuple(specs)


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
