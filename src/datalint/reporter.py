"""reporter: 质检统计聚合与 JSON/表格两种格式渲染."""

from __future__ import annotations

import json

from datalint.schema import ALL_ERROR_TYPES


class Report:
    """一次处理的统计累计器.

    不变量: total == passed + rejected; rejected == sum(errors.values()).
    (由 count_pass / count_reject 各自同步递增 total 保证)
    """

    def __init__(self) -> None:
        self.total = 0
        self.passed = 0
        self.errors: dict[str, int] = {error_type: 0 for error_type in ALL_ERROR_TYPES}

    @property
    def rejected(self) -> int:
        return sum(self.errors.values())

    def count_pass(self) -> None:
        self.total += 1
        self.passed += 1

    def count_reject(self, error_type: str) -> None:
        self.total += 1
        self.errors[error_type] += 1


def render_json(report: Report) -> str:
    """渲染为机器可读 JSON, 键序固定, 六个错误键全部出现."""
    payload = {
        "total": report.total,
        "passed": report.passed,
        "rejected": report.rejected,
        "errors": {error_type: report.errors[error_type] for error_type in ALL_ERROR_TYPES},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_table(report: Report) -> str:
    """渲染为人类可读等宽文本表格, 数字列右对齐."""
    summary_rows = [
        ("total", report.total),
        ("passed", report.passed),
        ("rejected", report.rejected),
    ]
    error_rows = [(error_type, report.errors[error_type]) for error_type in ALL_ERROR_TYPES]

    lines = ["datalint report", "==============="]
    lines.extend(_format_rows(summary_rows))
    lines.append("")

    error_table = _format_rows(error_rows, header=("error type", "count"))
    lines.extend(error_table)
    return "\n".join(lines)


def _format_rows(
    rows: list[tuple[str, int]], header: tuple[str, str] | None = None
) -> list[str]:
    """左列名称左对齐, 右列数字右对齐; 可选表头与分隔线."""
    names = [name for name, _ in rows]
    values = [str(value) for _, value in rows]
    if header is not None:
        names.append(header[0])
        values.append(header[1])
    name_width = max(len(name) for name in names)
    value_width = max(len(value) for value in values)

    def fmt(name: str, value: str) -> str:
        return f"{name.ljust(name_width)}  {value.rjust(value_width)}"

    lines = []
    if header is not None:
        lines.append(fmt(header[0], header[1]))
        lines.append("-" * (name_width + 2 + value_width))
    lines.extend(fmt(name, str(value)) for name, value in rows)
    return lines
