# CLI 契约: datalint v2（相对 v1 的增量）

**日期**: 2026-09-10 | **分支**: `002-schema-csv-mask` | **基线**: [v1 契约](../../001-datalint-cli/contracts/cli-contract.md)

## 命令签名（v2 完整版）

```
datalint INPUT [-o OUTPUT] [--rejects REJECTS] [--dedup-by FIELD[,FIELD...]]
         [--report-format {table,json}] [--report-file PATH]
         [--schema PATH] [--input-format {jsonl,csv}] [--output-format {jsonl,csv}]
         [--mask PATTERN[:MODE][,PATTERN[:MODE]...]]...
```

v1 全部选项、退出码、报告契约、剔除明细格式不变。**所有新选项缺省时行为与 v1 逐字节一致。**

## 新增参数

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `--schema` | 否 | 内置 schema | 外部 schema JSON 文件路径；加载并校验通过后完全替代内置 schema |
| `--input-format` | 否 | 自动识别 | 显式指定输入格式，跳过自动识别 |
| `--output-format` | 否 | `jsonl` | 干净数据输出格式 |
| `--mask` | 否 | 不脱敏 | 可重复给出；每项为逗号分隔的 `PATTERN[:MODE]` 列表，MODE ∈ equal(默认)/contain |

**默认输出路径随输出格式**: `--output-format csv` 时默认输出 `<基底>.clean.csv`；`-o` 显式指定时原样使用。剔除明细路径规则不变（恒为 `<基底>.rejects.jsonl`，JSONL 格式）。**基底派生规则**：输入扩展名为 `.jsonl`/`.json` 时剥离扩展名（`a.jsonl` → `a`）；其他扩展名保留完整文件名（`a.csv` → `a.csv`），避免同名不同扩展输入的输出互相覆盖。

**Bugfix**: 2026-09-11 — [BUG-005] 基底派生规则修订。

## 新增/变更行为契约

### 外部 schema

| 场景 | 行为 |
|------|------|
| `--schema` 文件不存在/不可读 | stderr 报错，退出码 1，不产生输出文件 |
| schema JSON 语法错误 | stderr 报 "schema 文件 JSON 解析失败: <原因>"，退出码 2，不产生输出文件 |
| schema 结构/内容非法（缺 fields、类型名非法、枚举缺取值、名称重复等） | stderr 报错并指明字段与原因、列出支持的类型（类型错误时），退出码 2 |
| schema 合法 | 校验/清洗/`--dedup-by` 合法性全部按该 schema；内置 schema 不生效 |

### 输入格式识别

| 场景 | 行为 |
|------|------|
| `--input-format` 显式指定 | 按指定格式读取，跳过识别 |
| 扩展名 `.csv` / `.jsonl` / `.json` | 按扩展名识别（不区分大小写） |
| 其他扩展名/无扩展名 | 嗅探首个非空行：JSON 对象 → jsonl；可解析 CSV 表头 → csv |
| 无法识别（含空文件） | stderr 报错并提示使用 `--input-format`，退出码 1 |

### CSV 输入

| 场景 | 行为 |
|------|------|
| 表头含空列名或重复列名 | stderr 报错，退出码 1 |
| 数据行列数 ≠ 表头列数 | 该行 `Rejection(parse_error, "列数不匹配: 期望 N 列, 实际 M 列")`，处理继续 |
| number 字段文本无法转数字 | 保留原字符串 → validator 报 type_error 剔除 |
| 空单元格 | 可选字段视为缺失；必填字段保留空字符串 |
| 只有表头无数据行 | 正常完成，total=0，退出码 0 |

### CSV 输出

- 表头 = 全部输出记录字段名的首见顺序并集；记录缺列输出空字符串。
- 标准逗号分隔、双引号转义、UTF-8；可被常规表格工具直接打开。
- 与 JSONL 输出承载的记录内容等价。

### --mask 脱敏

| 场景 | 行为 |
|------|------|
| `--mask email:equal --mask phone:contain` | 两条规则并存；可混用模式；等价于 `--mask email:equal,phone:contain` |
| `--mask email`（无 MODE） | 等价于 `email:equal` |
| equal 匹配 | 字段名区分大小写精确相等 |
| contain 匹配 | 字段名不区分大小写包含子串；匹配范围含 schema 外透传字段 |
| 命中字段值为字符串 | 长度 > 4：保留首尾各 1 字符中间 `*` 等长填充；长度 1–4：全 `*`；空串不变 |
| 命中字段值非字符串 / 字段缺失 | 原样，不报错 |
| 非法 MODE（如 `email:fuzzy`）或空 PATTERN（如 `--mask ,` 或 `:equal`） | stderr 报错，退出码 2 |
| 与 `--dedup-by` 同字段 | 去重按脱敏前真实值判定；仅输出被掩码 |
| 报告 | 有无 `--mask` 报告统计完全一致 |

## 行为示例

```bash
# 自定义 schema + CSV 输入自动识别 + CSV 输出
datalint users.csv --schema my_schema.json --output-format csv

# 显式指定格式（文件无扩展名）
datalint /data/export --input-format csv -o clean.jsonl

# 混合模式脱敏：email 精确、phone 模糊(命中 phone/home_phone/PhoneNumber)
datalint data.jsonl --mask email:equal --mask phone:contain

# 合写等价形式
datalint data.jsonl --mask "email,phone:contain"

# 非法 schema → 退出码 2
datalint data.jsonl --schema broken.json
```

## 退出码（不变，新增场景归类）

| 码 | v2 新增场景 |
|----|-------------|
| 0 | CSV 输入含任意比例损坏行处理完成 |
| 1 | schema 文件不存在/不可读；格式无法识别；CSV 表头非法 |
| 2 | schema 内容非法；非法 `--input-format`/`--output-format` 取值；非法 `--mask` 模式/空模式；`--dedup-by` 字段不在生效 schema 中 |
