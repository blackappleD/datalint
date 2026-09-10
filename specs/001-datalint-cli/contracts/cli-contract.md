# CLI 契约: datalint

**日期**: 2026-09-10 | **分支**: `001-datalint-cli`

## 命令签名

```
datalint INPUT [-o OUTPUT] [--rejects REJECTS] [--dedup-by FIELD[,FIELD...]]
         [--report-format {table,json}] [--report-file PATH]
```

亦可通过 `python -m datalint ...` 调用，行为完全一致。

## 参数

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `INPUT` | 是 | — | 输入 JSONL 文件路径 |
| `-o, --output` | 否 | `<INPUT 去扩展名>.clean.jsonl` | 干净数据输出路径 |
| `--rejects` | 否 | `<INPUT 去扩展名>.rejects.jsonl` | 剔除明细输出路径（与输出同目录，澄清 Q2） |
| `--dedup-by` | 否 | 不去重 | 逗号分隔的去重字段；每个字段必须在 schema 中定义，否则参数错误（澄清 Q4） |
| `--report-format` | 否 | `table` | 报告格式：`table`（人类可读）或 `json`（机器可读） |
| `--report-file` | 否 | 输出到 stdout | 报告写入文件而非 stdout |

## 输出流约定

| 流 | 内容 |
|----|------|
| stdout | 质检报告（未指定 `--report-file` 时） |
| stderr | 错误信息（文件不存在、参数非法等） |
| `OUTPUT` 文件 | 干净 JSONL，UTF-8，每行一条，`ensure_ascii=False` |
| `REJECTS` 文件 | 剔除明细 JSONL：`{"line", "error_type", "reason", "record"}` |

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 处理成功完成（即使 100% 记录被剔除——剔除是正常质检结果） |
| 1 | 运行错误：输入文件不存在/不可读、输出不可写 |
| 2 | 参数错误：argparse 校验失败、`--dedup-by` 含非 schema 字段 |

## 报告契约

### JSON 格式（`--report-format json`）

```json
{
  "total": 100,
  "passed": 90,
  "rejected": 10,
  "errors": {
    "parse_error": 2,
    "missing_field": 3,
    "type_error": 1,
    "enum_error": 1,
    "timestamp_invalid": 1,
    "duplicate": 2
  }
}
```

- 六个错误键始终全部出现（计数为 0 也保留）。
- 不变量：`total == passed + rejected`，`rejected == sum(errors.values())`。

### 表格格式（`--report-format table`，默认）

```
datalint report
===============
total     100
passed     90
rejected   10

error type          count
-------------------------
parse_error             2
missing_field           3
type_error              1
enum_error              1
timestamp_invalid       1
duplicate               2
```

数字列右对齐；两种格式的统计数字必须一致（FR-009）。

## 行为示例

```bash
# 最简调用：默认输出路径 + 表格报告到 stdout
datalint data.jsonl

# 指定输出、按 id 去重、JSON 报告写入文件
datalint data.jsonl -o clean.jsonl --dedup-by id --report-format json --report-file report.json

# 多字段去重
datalint data.jsonl --dedup-by name,category

# 参数错误示例（nonfield 不在 schema 中）→ stderr 报错，退出码 2
datalint data.jsonl --dedup-by nonfield
```

## 边界行为契约

| 场景 | 行为 |
|------|------|
| 输入文件不存在 | stderr 明确报错，退出码 1，不产生输出文件 |
| 输入为空文件（0 行） | 正常完成：空输出文件、空剔除文件、total=0 报告，退出码 0 |
| 全部记录非法 | 正常完成：空输出文件、明细含全部记录，退出码 0 |
| 空白行 | 跳过，不计入 total |
| 未指定 `--dedup-by` | 不去重，`duplicate` 计数恒为 0 |
