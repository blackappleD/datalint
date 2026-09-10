# datalint 开发指南

基于所有功能计划自动生成. 最后更新时间: 2026-09-10

## 活跃技术

- Python 3.10+，仅标准库（`argparse`、`json`、`datetime`、`pathlib`、`dataclasses`、`collections`）
- 测试：pytest（唯一开发依赖）
- 打包：pyproject.toml（setuptools，src 布局，console_scripts 入口 `datalint`）

## 项目结构

```text
src/datalint/
├── __init__.py      # 版本号
├── __main__.py      # python -m datalint 入口
├── cli.py           # argparse 参数解析、模块编排、退出码
├── schema.py        # 内置(默认) schema + load_schema 外部加载校验 + 错误类型常量
├── reader.py        # 格式识别(扩展名优先+嗅探)、JSONL/CSV 流式读取、CSV 类型转换
├── validator.py     # 必填/类型/枚举校验(接收 schema 参数)
├── cleaner.py       # 去空白、时间戳归一、按字段去重(接收 schema 参数)
├── masker.py        # --mask 规则解析(pattern:equal|contain)与掩码应用
├── reporter.py      # 统计聚合 + JSON/表格渲染
└── writer.py        # JSONL 流式写出; CSV 两遍法写出(列集合首见顺序并集)
tests/               # pytest 单元测试 + test_cli.py 端到端
specs/001-datalint-cli/   # v1 规范文档
specs/002-schema-csv-mask/ # v2 规范文档(外部 schema/CSV/脱敏)
```

## 命令

```bash
pip install -e ".[dev]"   # 安装（含 pytest）
datalint INPUT [-o OUTPUT] [--rejects PATH] [--dedup-by FIELDS] \
  [--report-format table|json] [--report-file PATH] \
  [--schema PATH] [--input-format jsonl|csv] [--output-format jsonl|csv] \
  [--mask PATTERN[:MODE][,...]]
pytest                    # 运行测试
```

## 代码风格

- Python：PEP 8，类型标注，冻结 dataclass 表示不可变数据（FieldSpec/Rejection）
- 不可变模式：清洗构建新 dict，不就地修改
- 流式处理：reader 产出生成器，管道逐条流过；仅去重键集合与计数器常驻内存
- 错误类型常量集中在 `schema.py`，validator/cleaner/reporter 共用
- 陷阱：`bool` 是 `int` 子类，number/timestamp 类型校验须显式排除 bool

## 最近变更

- 002-schema-csv-mask: 外部 JSON schema 加载与自校验(管道 schema 参数化)、CSV 输入(自动识别+类型转换)/输出(两遍法)、--mask 脱敏(equal/contain 混用、首尾保留掩码、dedup 后应用)
- 001-datalint-cli: JSONL 数据清洗与质检 CLI——schema 校验（必填/类型/枚举）、清洗（去空白/时间戳归一 ISO 8601 UTC/按字段去重）、剔除明细文件、JSON/表格双格式质检报告

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
