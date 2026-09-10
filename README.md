# datalint

清洗和质检结构化 JSONL 数据集的 Python 命令行工具——仅依赖标准库。

- **校验**: 按内置 schema 检查必填字段、字段类型、枚举取值，非法记录剔除并记录原因
- **清洗**: 字符串去首尾空白、时间戳统一为 ISO 8601 UTC、按指定字段去重（保留首次出现）
- **输出**: 干净的 JSONL + 剔除明细 JSONL + 质检报告（JSON 或表格格式）

## 安装

需要 Python 3.10+。在仓库根目录执行：

```bash
pip install -e .
```

含开发依赖（pytest）：

```bash
pip install -e ".[dev]"
```

安装后可通过 `datalint` 命令或 `python -m datalint` 调用。

## 内置 schema

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | 字符串 | 是 | |
| `name` | 字符串 | 是 | |
| `category` | 枚举 | 是 | 允许值: `A` / `B` / `C` |
| `score` | 数字 | 否 | bool 不视为数字 |
| `timestamp` | 时间戳 | 是 | 支持 ISO 8601 变体、`YYYY/MM/DD HH:MM:SS`、Unix 秒级时间戳 |

schema 未定义的额外字段原样透传（字符串同样去首尾空白），不参与校验。
schema 集中定义在 [src/datalint/schema.py](src/datalint/schema.py)，修改字段只需改这一处。

## 用法

```bash
datalint INPUT [-o OUTPUT] [--rejects REJECTS] [--dedup-by FIELD[,FIELD...]]
         [--report-format {table,json}] [--report-file PATH]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `INPUT` | — | 输入 JSONL 文件路径（必需） |
| `-o, --output` | `<输入名>.clean.jsonl` | 干净数据输出路径 |
| `--rejects` | `<输入名>.rejects.jsonl` | 剔除明细输出路径 |
| `--dedup-by` | 不去重 | 逗号分隔的去重字段（必须是 schema 字段） |
| `--report-format` | `table` | 报告格式：`table` 或 `json` |
| `--report-file` | 输出到 stdout | 报告写入文件 |

退出码：`0` 处理成功（即使全部记录被剔除）；`1` 运行错误（文件不存在/不可写）；`2` 参数错误。

## 运行示例

准备一份脏数据 `demo.jsonl`：

```jsonl
{"id": "1", "name": "  Alice  ", "category": "A", "score": 95, "timestamp": "2026/09/10 08:00:00"}
{"id": "2", "name": "Bob", "category": "X", "timestamp": "2026-09-10T08:00:00Z"}
{"id": "3", "category": "B", "timestamp": 1789027200}
{"id": "1", "name": "Alice", "category": "A", "timestamp": "2026-09-10T09:00:00+00:00"}
not valid json
```

运行：

```bash
datalint demo.jsonl --dedup-by id
```

结果：

- `demo.clean.jsonl` — 1 条干净记录（第 1 行）：`name` 去除空白为 `"Alice"`，时间戳归一为 `"2026-09-10T08:00:00Z"`
- `demo.rejects.jsonl` — 4 条明细：第 2 行 `enum_error`、第 3 行 `missing_field`（缺 name）、第 4 行 `duplicate`（id 重复）、第 5 行 `parse_error`
- stdout 表格报告：

```
datalint report
===============
total     5
passed    1
rejected  4

error type         count
------------------------
parse_error            1
missing_field          1
type_error             0
enum_error             1
timestamp_invalid      1
duplicate              1
```

JSON 报告（适合流水线消费）：

```bash
datalint demo.jsonl --dedup-by id --report-format json --report-file report.json
```

```json
{
  "total": 5,
  "passed": 1,
  "rejected": 4,
  "errors": {
    "parse_error": 1,
    "missing_field": 1,
    "type_error": 0,
    "enum_error": 1,
    "timestamp_invalid": 1,
    "duplicate": 1
  }
}
```

剔除明细每行格式：

```json
{"line": 3, "error_type": "missing_field", "reason": "缺失必填字段: name", "record": {"id": "3", "category": "B", "timestamp": 1789027200}}
```

## 项目结构

```
src/datalint/
├── cli.py        # 参数解析与管道编排
├── schema.py     # 内置 schema 与共享类型
├── reader.py     # 逐行流式读取与 JSON 解析
├── validator.py  # 必填/类型/枚举校验
├── cleaner.py    # 去空白、时间戳归一、去重
└── reporter.py   # 统计聚合与 JSON/表格渲染
```

大文件按行流式处理，内存占用不随文件大小膨胀（仅去重键集合与计数器常驻内存）。

## 运行测试

```bash
pytest              # 全部测试
pytest -m "not slow"  # 跳过性能测试
```
