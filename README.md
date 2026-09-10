# datalint

清洗和质检结构化数据集（JSONL / CSV）的 Python 命令行工具——仅依赖标准库。

- **校验**: 按 schema（内置或外部 JSON 文件）检查必填字段、字段类型、枚举取值，非法记录剔除并记录原因
- **清洗**: 字符串去首尾空白、时间戳统一为 ISO 8601 UTC（保留亚秒精度；无时区输入按 UTC 处理并在结束时告警）、按指定字段去重（保留首次出现；去重字段缺失的记录跳过去重）
- **脱敏**: `--mask` 对指定字段做掩码，支持精确（equal）与模糊（contain）两种匹配模式
- **输出**: 干净数据（JSONL 或 CSV）+ 剔除明细 JSONL + 质检报告（JSON 或表格格式）

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

## schema

### 内置 schema（默认）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | 字符串 | 是 | |
| `name` | 字符串 | 是 | |
| `category` | 枚举 | 是 | 允许值: `A` / `B` / `C` |
| `score` | 数字 | 否 | bool 不视为数字 |
| `timestamp` | 时间戳 | 是 | 支持 ISO 8601 变体、`YYYY/MM/DD HH:MM:SS`、Unix 秒级时间戳 |

schema 未定义的额外字段原样透传（字符串同样去首尾空白），不参与校验。可选字段（required: false）同时是 nullable 的——显式 `null` 不报类型错误，原样保留在输出中；必填字段的 `null` 仍按类型错误剔除。
内置 schema 定义在 [src/datalint/schema.py](src/datalint/schema.py)。

### 外部 schema（`--schema my_schema.json`）

编写一个 JSON 文件即可让工具适配任意结构的数据集，完全替代内置 schema：

```json
{
  "fields": [
    {"name": "user_id", "type": "string", "required": true},
    {"name": "level", "type": "enum", "required": true, "enum_values": ["gold", "silver"]},
    {"name": "amount", "type": "number"},
    {"name": "created_at", "type": "timestamp", "required": true}
  ]
}
```

- 支持的类型：`string` / `number` / `timestamp` / `enum`
- `required` 缺省为 false；`enum_values` 仅枚举类型必须提供（非空字符串数组）
- schema 文件本身在处理开始前完整校验：JSON 语法、字段名非空且不重复、类型名合法、枚举取值完整——任何问题都会给出指明字段与原因的报错（退出码 2），不产生任何输出文件

## 用法

```bash
datalint INPUT [-o OUTPUT] [--rejects REJECTS] [--dedup-by FIELD[,FIELD...]]
         [--report-format {table,json}] [--report-file PATH]
         [--schema PATH] [--input-format {jsonl,csv}] [--output-format {jsonl,csv}]
         [--mask PATTERN[:MODE][,...]]...
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `INPUT` | — | 输入文件路径，JSONL 或 CSV（必需） |
| `-o, --output` | `<基底>.clean.<输出格式>` | 干净数据输出路径；基底 = 输入名去 `.jsonl`/`.json` 扩展名，其他扩展名保留完整文件名（`a.csv` → `a.csv.clean.jsonl`，避免与 `a.jsonl` 的输出冲突） |
| `--rejects` | `<基底>.rejects.jsonl` | 剔除明细输出路径（恒为 JSONL） |
| `--dedup-by` | 不去重 | 逗号分隔的去重字段（必须在生效 schema 中） |
| `--report-format` | `table` | 报告格式：`table` 或 `json` |
| `--report-file` | 输出到 stdout | 报告写入文件 |
| `--schema` | 内置 schema | 外部 schema JSON 文件路径 |
| `--input-format` | 自动识别 | 显式指定输入格式（扩展名 `.csv`/`.jsonl`/`.json` 自动识别，其他嗅探内容） |
| `--output-format` | `jsonl` | 干净数据输出格式 |
| `--mask` | 不脱敏 | 脱敏字段模式，可重复；`MODE` 为 `equal`（默认，精确）或 `contain`（模糊，不区分大小写） |

退出码：`0` 处理成功（即使全部记录被剔除，损坏行不会中断处理）；`1` 运行错误（文件不存在/格式无法识别/CSV 表头非法）；`2` 参数错误（含非法 schema 内容、非法 `--mask` 模式）。

## CSV 支持

- 输入：带表头的标准逗号分隔 CSV（UTF-8，自动剥离 BOM——JSONL 输入同样支持带 BOM 文件）；数字字段按 schema 自动转换类型，转换失败按类型错误剔除；列数与表头不符的行剔除并记录原因，处理不中断
- 输出：`--output-format csv` 产出带表头的 CSV，列为全部记录字段的首见顺序并集，缺失值输出为空

```bash
# CSV 进 CSV 出 + 自定义 schema
datalint users.csv --schema my_schema.json --output-format csv

# 无扩展名文件显式指定格式
datalint /data/export --input-format csv
```

## 脱敏

```bash
# email 精确匹配、phone 模糊匹配(同时命中 phone/home_phone/PhoneNumber)
datalint data.jsonl --mask email:equal --mask phone:contain

# 逗号合写等价形式
datalint data.jsonl --mask "email,phone:contain"
```

掩码规则：值长度 > 4 保留首尾各 1 字符、中间以等长 `*` 填充（`alice@example.com` → `a***************m`）；长度 ≤ 4 全掩码。脱敏只影响输出——去重、校验、报告均按脱敏前的真实值判定。

> **注意**：剔除明细文件（`*.rejects.jsonl`）为便于人工回溯，始终保留被剔除记录的**原始未脱敏值**（包括因重复被剔除的合法记录）。如果剔除明细也需要脱敏交付，请勿直接分发该文件。

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
timestamp_invalid      0
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
    "timestamp_invalid": 0,
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
├── schema.py     # 内置/外部 schema 与共享类型
├── reader.py     # 格式识别、JSONL/CSV 流式读取
├── validator.py  # 必填/类型/枚举校验
├── cleaner.py    # 去空白、时间戳归一、去重
├── masker.py     # --mask 脱敏规则与掩码
├── reporter.py   # 统计聚合与 JSON/表格渲染
└── writer.py     # JSONL/CSV 输出(两遍法)
```

大文件按行流式处理，内存占用不随文件大小膨胀（仅去重键集合与计数器常驻内存）。

## 运行测试

```bash
pytest              # 全部测试
pytest -m "not slow"  # 跳过性能测试
```
