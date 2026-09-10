# 数据模型: datalint

**日期**: 2026-09-10 | **分支**: `001-datalint-cli` | **来源**: [spec.md](./spec.md) 关键实体 + [research.md](./research.md)

## 实体

### FieldSpec（schema 字段定义）

内置 schema 的单字段声明，定义于 `schema.py`，冻结 dataclass。

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | str | 字段名 |
| `type` | str | `"string"` \| `"number"` \| `"timestamp"` \| `"enum"` 之一 |
| `required` | bool | 是否必填 |
| `enum_values` | frozenset[str] \| None | 仅 `type == "enum"` 时非空 |

**内置 SCHEMA 常量**（澄清 Q1 确定）:

| name | type | required | enum_values |
|------|------|----------|-------------|
| `id` | string | 是 | — |
| `name` | string | 是 | — |
| `category` | enum | 是 | `{"A", "B", "C"}` |
| `score` | number | 否 | — |
| `timestamp` | timestamp | 是 | — |

**校验规则**（validator 按序执行，首错即剔）:
1. 必填字段存在性：`required and name not in record` → `missing_field`
2. 类型正确性：
   - `string` → `isinstance(v, str)`
   - `number` → `isinstance(v, (int, float)) and not isinstance(v, bool)`
   - `enum` → `isinstance(v, str)`
   - `timestamp` → `isinstance(v, (str, int, float)) and not isinstance(v, bool)`（可解析性由 cleaner 判定）
   失败 → `type_error`
3. 枚举合法性：`v in enum_values`，失败 → `enum_error`
4. schema 未定义的额外字段：跳过，不校验、不剔除（澄清 Q5）

### Record（记录）

JSONL 一行解析出的 `dict[str, Any]`（JSON 对象）。非对象的合法 JSON（数组、标量）视为解析失败。贯穿管道的形态：

```
原始行 (str) → 解析记录 (dict) → 已校验记录 → 已清洗记录 (dict) → 输出行 (str)
```

**清洗转换**（不可变风格——构建新 dict，不就地修改）:
- 所有字符串值（含 schema 外字段）：`v.strip()`
- `timestamp` 字段：按 R2 三段式解析 → `"YYYY-MM-DDTHH:MM:SSZ"`（UTC）；失败 → `timestamp_invalid`

### Rejection（剔除项）

一条被剔除记录的元信息，冻结 dataclass，序列化为剔除明细 JSONL 的一行。

| 属性 | 类型 | 说明 |
|------|------|------|
| `line` | int | 源文件行号（从 1 起） |
| `error_type` | str | ErrorType 之一 |
| `reason` | str | 人类可读原因，含字段名/期望值/实际值 |
| `record` | dict \| str | 原始记录；解析失败时为原始行文本 |

### ErrorType（错误类型枚举）

定义于 `schema.py`，validator / cleaner / reporter 共用的字符串常量：

| 值 | 产生者 | 触发条件 |
|----|--------|----------|
| `parse_error` | reader | 行无法解析为 JSON 对象 |
| `missing_field` | validator | 必填字段缺失 |
| `type_error` | validator | 字段类型不符 |
| `enum_error` | validator | 枚举取值非法 |
| `timestamp_invalid` | cleaner | 时间戳无法按三类格式解析 |
| `duplicate` | cleaner | 去重键与先前记录重复 |

### Report（质检报告）

一次运行的统计聚合，由 reporter 从处理流增量累计。

| 属性 | 类型 | 说明 |
|------|------|------|
| `total` | int | 输入记录总数（不含跳过的空白行） |
| `passed` | int | 写入干净输出的记录数 |
| `rejected` | int | 剔除总数 |
| `errors` | dict[str, int] | 六类 ErrorType → 计数（含 0 值键） |

**不变量**（SC-004）: `total == passed + rejected`；`rejected == sum(errors.values())`。

**渲染**: JSON（固定键序，`indent=2`, `ensure_ascii=False`）或等宽文本表格，两者数字必须一致。

## 状态转换

```
每行输入
  ├─ 空白行 ──────────────────────────────→ 跳过（不计数）
  └─ 计入 total
      ├─ JSON 解析失败 ──→ Rejection(parse_error) ─┐
      ├─ 校验失败 ───────→ Rejection(missing_field │ type_error │ enum_error) ─┤
      ├─ 时间戳不可解析 ─→ Rejection(timestamp_invalid) ─┤
      ├─ 去重键重复 ─────→ Rejection(duplicate) ─────────┤
      │                                                  ↓
      │                                      剔除明细文件 + errors 计数
      └─ 通过 ──→ 清洗后记录 ──→ 干净输出文件 + passed 计数
```

## 关系

- SCHEMA (1) ←验证依据— Record (N)
- Record (1) —失败产出→ Rejection (0..1)（首错即剔，最多一条）
- 处理流 (1) —聚合→ Report (1)
- Report.errors 的键 ≡ ErrorType 全集（一致性由共享常量保证）
