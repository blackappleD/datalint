# 实施计划: datalint — JSONL 数据清洗与质检 CLI

**分支**: `001-datalint-cli` | **日期**: 2026-09-10 | **规范**: [spec.md](./spec.md)
**输入**: 来自 `/specs/001-datalint-cli/spec.md` 的功能规范

## 摘要

datalint 是一个纯标准库实现的 Python CLI：逐行流式读取 JSONL 文件，按内置 schema（id/name/category/score/timestamp）校验必填字段、类型与枚举值，剔除非法记录并写入剔除明细文件；对合法记录执行清洗（字符串去首尾空白、时间戳统一为 ISO 8601 UTC、按指定字段去重保留首现）；输出干净 JSONL 与质检报告（JSON 或表格格式）。代码按 reader / validator / cleaner / reporter 四模块拆分，pytest 单元测试覆盖核心路径。

## 技术背景

**语言/版本**: Python 3.10+（使用 `datetime.fromisoformat`、类型标注；不依赖 3.11+ 特性以保证兼容面）
**主要依赖**: 仅标准库（`argparse`、`json`、`datetime`、`pathlib`、`dataclasses`、`collections`）
**存储**: 文件（JSONL 输入/输出、剔除明细 JSONL、可选报告文件）
**测试**: pytest（唯一开发依赖）
**目标平台**: 跨平台命令行（Windows / Linux / macOS）
**项目类型**: 单一 CLI 项目（src 布局的 Python 包）
**性能目标**: 10 万行输入 60 秒内完成（SC-005）
**约束条件**: 逐行流式处理，内存占用不随文件大小线性膨胀（去重键集合与统计计数器除外）；UTF-8 编码；离线可用
**规模/范围**: 单一内置 schema；4 个核心模块 + CLI 入口；约 6 类错误分类

## 章程检查

*门控: 必须在阶段 0 研究前通过. 阶段 1 设计后重新检查.*

`.specify/memory/constitution.md` 尚为未填充模板，无项目特定门控条款。采用通用门控评估：

| 门控 | 状态 | 说明 |
|------|------|------|
| 简洁性（最小可行结构） | PASS | 单一项目、无框架、无外部依赖；四模块拆分由用户明确要求 |
| CLI 文本协议 | PASS | 输入为文件参数，干净数据/报告输出到文件或 stdout，错误到 stderr，支持 JSON + 人类可读格式 |
| 测试优先 | PASS | 每个模块先写 pytest 单测（RED→GREEN），验收场景映射为测试用例 |
| 可观测性 | PASS | 剔除明细文件 + 分类计数报告即结构化可追溯输出 |

**阶段 1 设计后复查**: PASS——设计未引入额外项目、抽象层或依赖。

## 项目结构

### 文档(此功能)

```
specs/001-datalint-cli/
├── plan.md              # 此文件
├── research.md          # 阶段 0 输出
├── data-model.md        # 阶段 1 输出
├── quickstart.md        # 阶段 1 输出
├── contracts/
│   └── cli-contract.md  # 阶段 1 输出：CLI 命令契约
└── tasks.md             # 阶段 2 输出 (/speckit.tasks 创建)
```

### 源代码(仓库根目录)

```
pyproject.toml           # 包元数据 + console_scripts 入口（无运行时依赖）
README.md                # 安装与运行示例
src/
└── datalint/
    ├── __init__.py      # 版本号
    ├── __main__.py      # python -m datalint 入口
    ├── cli.py           # argparse 参数解析、模块编排、退出码
    ├── schema.py        # 内置 schema 定义（集中一处）+ 错误类型常量
    ├── reader.py        # 逐行流式读取与 JSON 解析（含行号、跳过空白行）
    ├── validator.py     # 必填/类型/枚举校验，产出 Rejection
    ├── cleaner.py       # 去空白、时间戳归一、按字段去重
    └── reporter.py      # 统计聚合 + JSON/表格渲染
tests/
├── conftest.py          # 共享 fixture（临时 JSONL 文件构造）
├── test_reader.py
├── test_validator.py
├── test_cleaner.py
├── test_reporter.py
└── test_cli.py          # 端到端：脏输入 → 干净输出 + 报告 + 退出码
```

**结构决策**: 采用 src 布局单包结构。`schema.py` 独立于 validator，因为 cleaner（时间戳字段识别）与 cli（去重字段合法性校验）也需要 schema 信息；四个处理模块与用户要求一一对应，`cli.py` 仅做编排不含业务逻辑。

## 复杂度跟踪

无章程违规，无需填写。
