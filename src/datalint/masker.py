"""masker: --mask 脱敏——规则解析、字段匹配与掩码应用.

脱敏仅作用于输出内容(在 dedup 之后应用), 不改变校验、去重、报告语义.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MODE_EQUAL = "equal"
MODE_CONTAIN = "contain"
_VALID_MODES = (MODE_EQUAL, MODE_CONTAIN)
_MASK_CHAR = "*"
_KEEP_EDGES_MIN_LENGTH = 5  # 值长度达到此值才保留首尾字符


@dataclass(frozen=True)
class MaskRule:
    """单条脱敏规则: 字段名模式 + 匹配模式."""

    pattern: str
    mode: str

    def matches(self, field_name: str) -> bool:
        if self.mode == MODE_EQUAL:
            return field_name == self.pattern
        return self.pattern.lower() in field_name.lower()


def parse_mask_rules(raw_list: Optional[list[str]]) -> tuple[MaskRule, ...]:
    """解析 --mask 参数值(argparse append 产生的列表, 每项可逗号合写).

    每段格式 `pattern[:mode]`, mode 缺省 equal; 非法 mode 或空 pattern 抛 ValueError.
    """
    if not raw_list:
        return ()
    rules: list[MaskRule] = []
    for raw in raw_list:
        for part in raw.split(","):
            pattern, _, mode = part.partition(":")
            pattern = pattern.strip()
            mode = mode.strip() or MODE_EQUAL
            if not pattern:
                raise ValueError(f"--mask 字段模式不能为空: {part!r}")
            if mode not in _VALID_MODES:
                allowed = "/".join(_VALID_MODES)
                raise ValueError(f"--mask 匹配模式非法: {mode!r} (支持: {allowed})")
            rules.append(MaskRule(pattern, mode))
    if not rules:
        raise ValueError("--mask 未包含任何有效字段模式")
    return tuple(rules)


def _mask_value(value: str) -> str:
    # 按 Unicode 码点计长与切分; 组合字符(如基字母+变音符)可能被拆开——
    # 对邮箱/电话等目标字段无影响, 属已接受边界
    if len(value) >= _KEEP_EDGES_MIN_LENGTH:
        return value[0] + _MASK_CHAR * (len(value) - 2) + value[-1]
    return _MASK_CHAR * len(value)


def apply_mask(record: dict, rules: tuple[MaskRule, ...]) -> dict:
    """对记录中命中规则的字符串字段值做掩码, 返回新 dict(不修改原记录).

    匹配范围为记录实际出现的所有字段(含 schema 外字段); 非字符串值原样.
    """
    if not rules:
        return record
    return {
        key: _mask_value(value)
        if isinstance(value, str) and any(rule.matches(key) for rule in rules)
        else value
        for key, value in record.items()
    }
