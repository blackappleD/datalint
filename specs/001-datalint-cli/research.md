# 研究: datalint — JSONL 数据清洗与质检 CLI

**日期**: 2026-09-10 | **分支**: `001-datalint-cli`

技术上下文无未解决的 NEEDS CLARIFICATION。以下为各技术决策点的研究结论。

## R1: CLI 参数解析

- **Decision**: 标准库 `argparse`，单命令（无子命令），`prog="datalint"`。
- **Rationale**: 仅标准库约束下的唯一成熟选择；功能为单一流水线，无需子命令层级；argparse 自带 `--help`、类型转换与错误退出（exit code 2）。
- **Alternatives considered**: `click`/`typer`（违反仅标准库约束，排除）；手写 `sys.argv` 解析（重复造轮子、无 help 生成，排除）；argparse 子命令模式（当前只有一个动作，YAGNI，排除）。

## R2: 时间戳解析与归一化

- **Decision**: 三段式识别，顺序尝试：
  1. **Unix 秒级时间戳**: 值为 `int`/`float`，或纯数字字符串 → `datetime.fromtimestamp(v, tz=timezone.utc)`；
  2. **ISO 8601 变体**: 字符串 → 预处理（`Z` 结尾替换为 `+00:00` 以兼容 Python 3.10 的 `fromisoformat`）后调用 `datetime.fromisoformat`；
  3. **斜杠格式**: `datetime.strptime(v, "%Y/%m/%d %H:%M:%S")`。
  无时区信息的输入视为 UTC；统一输出 `dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`。三段全部失败 → 该记录剔除（错误类型 `timestamp_invalid`）。
- **Rationale**: `fromisoformat` 在 3.11+ 原生支持 `Z` 后缀，但为兼容 3.10 需要预处理；strptime 精确匹配澄清限定的斜杠格式，不做模糊猜测，保证行为可预测、可测试。裸数字字符串按 Unix 时间戳优先解释，避免与 ISO 歧义（ISO 纯数字形式如 `20260910` 罕见于脏数据且澄清未要求）。
- **Alternatives considered**: `dateutil.parser`（第三方，排除）；`time.strptime` 多格式循环遍历大格式表（超出澄清限定的三类范围，行为不可预测，排除）；正则手写解析（fromisoformat 已覆盖，排除）。

## R3: JSONL 流式读取

- **Decision**: `open(path, encoding="utf-8")` 文本迭代器逐行读取 + `json.loads`；reader 产出生成器 `Iterator[tuple[int, dict] | Rejection]`（行号从 1 计）；空白行 `line.strip() == ""` 直接跳过；解析产物非 JSON 对象（如数组、标量）视为解析失败。
- **Rationale**: 文件对象本身就是惰性行迭代器，天然满足流式与内存约束（SC-005）；生成器管道让 reader→validator→cleaner 逐条流过，只有去重键集合和计数器常驻内存。
- **Alternatives considered**: `readlines()` 全量载入（违反内存约束，排除）；`ijson`（第三方，排除）；按块手动分割换行（文本迭代器已足够，排除）。

## R4: 表格报告渲染

- **Decision**: 手写等宽文本表格：计算每列最大显示宽度，`str.ljust`/`rjust` 对齐，`-` 分隔线。报告两节：汇总（总数/通过/剔除）+ 错误分类计数表。
- **Rationale**: 标准库无表格库；数据形状固定（两列：指标名/计数），手写 ~20 行即可，可精确控制输出以便测试断言。
- **Alternatives considered**: `tabulate`/`rich`（第三方，排除）；`csv` 输出（不是"人类可读表格"，排除）；固定宽度硬编码（计数位数可变会破版，排除）。

## R5: JSON 报告与剔除明细格式

- **Decision**: JSON 报告用 `json.dumps(report, ensure_ascii=False, indent=2)`，结构：`{"total": int, "passed": int, "rejected": int, "errors": {"parse_error": int, "missing_field": int, "type_error": int, "enum_error": int, "timestamp_invalid": int, "duplicate": int}}`。剔除明细每行：`{"line": int, "error_type": str, "reason": str, "record": <原始记录或原始行文本>}`（解析失败时 `record` 为原始行字符串）。
- **Rationale**: 固定键名便于流水线消费与测试断言；`ensure_ascii=False` 保证中文原因描述可读；错误类型枚举集中定义在 `schema.py`，reporter 与 validator 共用，保证报告键与剔除明细的 `error_type` 一致。
- **Alternatives considered**: 报告含逐条剔除列表（与澄清决定"报告仅含分类计数"冲突，排除）；CSV 明细（记录是嵌套 JSON，JSONL 更自然，排除）。

## R6: schema 表示与校验

- **Decision**: `schema.py` 中以 `dataclass(frozen=True)` 的 `FieldSpec(name, type, required, enum_values)` 元组常量定义 schema；类型用标记字符串（`"string" | "number" | "timestamp" | "enum"`）映射到校验函数。`bool` 显式排除在 `number` 之外（Python 中 `bool` 是 `int` 子类，需 `type(v) in (int, float)` 或 `isinstance(v, bool)` 前置排除）。
- **Rationale**: 冻结 dataclass 满足不可变约定；声明式 schema 使"集中定义一处以便修改"（规范关键实体要求）成立；bool/int 陷阱是 Python 类型校验的经典坑，必须显式处理并配测试。
- **Alternatives considered**: JSON Schema 文档 + 手写解释器（过度设计，排除）；`jsonschema` 库（第三方，排除）；在 validator 内硬编码 if 链（schema 无法被 cleaner/cli 复用，排除）。

## R7: 去重实现

- **Decision**: cleaner 维护 `set[tuple]`，键为 `tuple(record.get(f, _MISSING) for f in dedup_fields)`，其中 `_MISSING` 为模块级哨兵对象（统一"缺失值"语义）；首现保留，后续同键记录产出 `duplicate` 类型 Rejection。去重发生在清洗（空白/时间戳归一）**之后**，保证 ` a ` 与 `a` 判为重复。
- **Rationale**: set 查重 O(1)，10 万行规模内存可控（仅存键元组）；清洗后去重的顺序让语义更符合"干净数据无重复"的直觉。字段值均为 JSON 标量（schema 校验后），tuple 可哈希。
- **Alternatives considered**: 清洗前去重（` a `/`a` 判为不同，产生输出重复，排除）；排序后相邻比较（破坏流式与原始顺序，排除）。

## R8: 打包与入口

- **Decision**: `pyproject.toml`（setuptools backend，src 布局），`[project.scripts] datalint = "datalint.cli:main"`；同时提供 `__main__.py` 支持 `python -m datalint`。运行时零依赖，`pytest` 列入 `[project.optional-dependencies] dev`。
- **Rationale**: pip 可安装 + 命令行入口是 README"安装、运行示例"的最简路径；打包工具不违反"仅标准库"约束（该约束指运行时依赖）。
- **Alternatives considered**: 单文件脚本无打包（无法满足四模块拆分与 pip 安装体验，排除）；`setup.py`（已过时，排除）。
