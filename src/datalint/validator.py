"""validator: 按内置 schema 校验记录(必填/类型/枚举), 首错即剔."""

from __future__ import annotations

from typing import Any, Optional

from datalint.schema import (
    ENUM_ERROR,
    MISSING_FIELD,
    TYPE_ENUM,
    TYPE_ERROR,
    TYPE_NUMBER,
    TYPE_STRING,
    TYPE_TIMESTAMP,
    FieldSpec,
    Rejection,
)


def _type_ok(spec: FieldSpec, value: Any) -> bool:
    if spec.type in (TYPE_STRING, TYPE_ENUM):
        return isinstance(value, str)
    if spec.type == TYPE_NUMBER:
        # bool 是 int 的子类, 必须显式排除
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if spec.type == TYPE_TIMESTAMP:
        # 可为 ISO/斜杠格式字符串或 Unix 秒级数字; 可解析性由 cleaner 判定
        return isinstance(value, (str, int, float)) and not isinstance(value, bool)
    return False


def validate(
    line_no: int, record: dict, schema: tuple[FieldSpec, ...]
) -> Optional[Rejection]:
    """按传入 schema 的声明顺序校验, 返回首个错误的 Rejection; 全部通过返回 None.

    schema 未定义的额外字段不参与校验.
    """
    for spec in schema:
        if spec.name not in record:
            if spec.required:
                return Rejection(
                    line_no, MISSING_FIELD, f"缺失必填字段: {spec.name}", record
                )
            continue
        value = record[spec.name]
        if value is None:
            # 可选字段显式 null 视同缺失语义, null 原样保留(BUG-006);
            # 必填字段不接受 null
            if spec.required:
                return Rejection(
                    line_no,
                    TYPE_ERROR,
                    f"字段 {spec.name} 类型错误: 期望 {spec.type}, 实际 null",
                    record,
                )
            continue
        if not _type_ok(spec, value):
            return Rejection(
                line_no,
                TYPE_ERROR,
                f"字段 {spec.name} 类型错误: 期望 {spec.type}, 实际 {type(value).__name__}",
                record,
            )
        if spec.type == TYPE_ENUM and value not in spec.enum_values:
            allowed = ", ".join(sorted(spec.enum_values))
            return Rejection(
                line_no,
                ENUM_ERROR,
                f"字段 {spec.name} 枚举值非法: {value!r} (允许值: {allowed})",
                record,
            )
    return None
