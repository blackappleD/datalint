# 实施计划: datalint v2 — 外部 schema、CSV 支持与字段脱敏

**分支**: `002-schema-csv-mask` | **日期**: 2026-09-10 | **规范**: [spec.md](./spec.md)
**输入**: 来自 `/specs/002-schema-csv-mask/spec.md` 的功能规范

## 摘要

在 v1 管道（reader → validator → cleaner → dedup → reporter）之上增加四项能力：(1) 外部 JSON schema 文件加载与自校验，管道从依赖模块级 SCHEMA 常量改为显式传递生效 schema；(2) CSV 输入（扩展名优先 + 内容嗅探自动识别、按 schema 类型转换文本值）与 JSONL/CSV 可选输出（CSV 输出采用两遍法以支持列集合动态并集）；(3) `--mask` 脱敏（每模式独立标注 equal/contain，统一首尾保留掩码，作用于全部实际字段、仅影响输出）；(4) 异常分支单元测试全覆盖。仍仅依赖标准库。

## 技术背景

**语言/版本**: Python 3.10+（不变）
**主要依赖**: 仅标准库；新增使用 `csv`（读写与方言）、复用 `json`/`argparse`/`dataclasses`/`datetime`/`re`
**存储**: 文件——新增外部 schema JSON 输入、CSV 输入/输出；剔除明细维持 JSONL
**测试**: pytest（不变），新增异常分支用例为显式需求（FR-112）
**目标平台**: 跨平台 CLI（不变）
**性能目标**: 沿用 SC-005（10 万行 60 秒内）；CSV 输出两遍法增加一次顺序磁盘读，仍满足目标
**约束条件**: 流式处理、内存 O(去重键 + 列集合 + 计数器)；UTF-8；v1 CLI 行为完全向后兼容（FR-101 场景 2、SC-107 零回归）
**规模/范围**: 4 个用户故事；修改 schema/reader/cli 三个既有模块，新增 masker 与 writer 两个模块

## 章程检查

*门控: 必须在阶段 0 研究前通过. 阶段 1 设计后重新检查.*

`.specify/memory/constitution.md` 仍为未填充模板，沿用 v1 采用的通用门控：

| 门控 | 状态 | 说明 |
|------|------|------|
| 简洁性 | PASS | 新增 masker/writer 两模块各承载单一职责（脱敏规则、输出渲染），避免 cli/cleaner 膨胀；无新依赖 |
| CLI 文本协议 | PASS | 新选项延续既有风格；错误仍走 stderr + 退出码 1/2 |
| 测试优先 | PASS | 延续 RED→GREEN；FR-112 显式要求异常分支覆盖 |
| 向后兼容 | PASS | 所有新选项均可选，缺省行为与 v1 逐字节一致；v1 测试套件作为回归门 |

**阶段 1 设计后复查**: PASS——两遍法 CSV 输出复用既有临时文件机制，schema 参数化重构不增加抽象层级。

## 项目结构

### 文档(此功能)

```
specs/002-schema-csv-mask/
├── plan.md              # 此文件
├── research.md          # 阶段 0 输出
├── data-model.md        # 阶段 1 输出
├── quickstart.md        # 阶段 1 输出
├── contracts/
│   └── cli-contract.md  # 阶段 1 输出：v2 CLI 契约增量
└── tasks.md             # 阶段 2 输出 (/speckit.tasks 创建)
```

### 源代码(仓库根目录)

```
src/datalint/
├── __init__.py          # 版本号 → 0.2.0
├── __main__.py          # 不变
├── cli.py               # [修改] 新选项 --schema/--input-format/--output-format/--mask; 编排注入生效 schema
├── schema.py            # [修改] 新增 load_schema(path) + SchemaValidationError; SCHEMA 更名语义为默认 schema
├── reader.py            # [修改] 格式识别 detect_format(); 新增 read_csv()(表头映射+类型转换+列数校验)
├── validator.py         # [修改] validate(line_no, record, schema) 接收 schema 参数
├── cleaner.py           # [修改] clean(line_no, record, schema) 时间戳字段来自 schema 参数
├── masker.py            # [新增] MaskRule 解析(pattern:mode)、字段匹配(equal/contain)、掩码算法
├── reporter.py          # 不变
└── writer.py            # [新增] JSONL 流式写出; CSV 两遍法写出(临时 JSONL + 列集合并集 → CSV)
tests/
├── conftest.py          # [修改] 新增 write_csv / write_schema fixture
├── test_schema_loading.py   # [新增] 外部 schema 加载与各类非法 schema
├── test_reader.py       # [修改] 格式识别 + CSV 读取/列数不匹配/类型转换
├── test_validator.py    # [修改] 适配 schema 参数(自定义 schema 用例)
├── test_cleaner.py      # [修改] 适配 schema 参数
├── test_masker.py       # [新增] 规则解析/匹配模式/掩码算法/非法参数
├── test_writer.py       # [新增] JSONL 与 CSV 输出、列集合并集、空值
├── test_cli.py          # [修改] v2 端到端: 外部 schema/CSV 双向/掩码/组合场景
└── test_performance.py  # 不变
```

**结构决策**: 管道组件从读取模块级 `SCHEMA` 常量改为显式接收 `schema` 参数（依赖注入），`SCHEMA` 保留为默认值——这是支持外部 schema 的最小重构，同时使自定义 schema 的单测不再依赖内置字段。`masker` 独立成模块（规则解析 + 应用是内聚职责，且 cleaner 语义是"质检清洗"而脱敏是"输出变换"）；`writer` 独立承载 JSONL/CSV 双格式与两遍法细节，保持 cli 纯编排。

## 复杂度跟踪

无章程违规。新增两个模块有明确单一职责，未引入投机抽象。
