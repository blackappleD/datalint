"""cleaner: 去除字符串首尾空白、时间戳归一为 ISO 8601 UTC、按字段去重."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional, Union

from datalint.schema import (
    DUPLICATE,
    MISSING,
    TIMESTAMP_INVALID,
    FieldSpec,
    Rejection,
    timestamp_fields,
)

_OUTPUT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_SLASH_FORMAT = "%Y/%m/%d %H:%M:%S"
_PLAIN_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def _from_unix(value: float) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _from_iso(text: str) -> Optional[datetime]:
    # Python 3.10 的 fromisoformat 不接受 Z 后缀, 预处理为 +00:00.
    # 注意: 3.10 还要求小数秒必须为 3 或 6 位(3.11+ 放开); 非常规位数的小数秒
    # 在 3.10 下会被判为 timestamp_invalid, 属于已知的受支持 ISO 子集边界.
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _from_slash(text: str) -> Optional[datetime]:
    try:
        return datetime.strptime(text, _SLASH_FORMAT)
    except ValueError:
        return None


def normalize_timestamp(value: Any) -> Optional[str]:
    """将时间戳归一为 ISO 8601 UTC 字符串; 无法识别返回 None.

    支持三类输入: Unix 秒级数字(int/float/纯数字字符串)、ISO 8601 变体、
    `YYYY/MM/DD HH:MM:SS`. 无时区信息的输入视为 UTC.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        dt = _from_unix(value)
    elif isinstance(value, str):
        text = value.strip()
        if _PLAIN_NUMBER.match(text):
            dt = _from_unix(float(text))
        else:
            dt = _from_iso(text) or _from_slash(text)
    else:
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(_OUTPUT_FORMAT)


def clean(
    line_no: int, record: dict, schema: tuple[FieldSpec, ...]
) -> Union[dict, Rejection]:
    """清洗一条已通过校验的记录, 返回新 dict(不修改原记录).

    - 所有字符串值(含 schema 外字段)去除首尾空白
    - 传入 schema 的时间戳字段归一为 ISO 8601 UTC; 失败返回 Rejection(timestamp_invalid)
    """
    cleaned = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in record.items()
    }
    for field in timestamp_fields(schema):
        if field not in cleaned:
            continue
        normalized = normalize_timestamp(cleaned[field])
        if normalized is None:
            return Rejection(
                line_no,
                TIMESTAMP_INVALID,
                f"字段 {field} 时间戳格式无法识别: {record[field]!r}",
                record,
            )
        cleaned[field] = normalized
    return cleaned


class Deduplicator:
    """按指定字段组合去重, 保留首次出现的记录.

    字段缺失时以 MISSING 哨兵参与键比较. 字段元组为空时不去重.
    """

    def __init__(self, fields: tuple[str, ...]):
        self._fields = tuple(fields)
        self._seen: set[tuple] = set()

    def check(self, line_no: int, record: dict) -> Optional[Rejection]:
        """首次出现返回 None 并记录键; 重复返回 Rejection(duplicate)."""
        if not self._fields:
            return None
        # 键值为 JSON 标量, tuple 可哈希; NaN 因 NaN != NaN 不会互判重复(接受的边界行为)
        key = tuple(record.get(field, MISSING) for field in self._fields)
        if key in self._seen:
            fields_desc = ", ".join(self._fields)
            return Rejection(
                line_no, DUPLICATE, f"按字段 ({fields_desc}) 去重: 与先前记录重复", record
            )
        self._seen.add(key)
        return None
