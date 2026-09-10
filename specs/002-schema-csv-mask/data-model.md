# 数据模型: datalint v2

**日期**: 2026-09-10 | **分支**: `002-schema-csv-mask` | **来源**: [spec.md](./spec.md) + [research.md](./research.md)

v1 实体（FieldSpec / Record / Rejection / ErrorType / Report）全部沿用，本文档只记录新增与变更。

## 新增实体

### 外部 Schema 文件（磁盘格式）

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

| 键 | 类型 | 约束 |
|----|------|------|
| `fields` | 数组 | 必须存在且非空 |
| `fields[].name` | str | 非空、全局不重复 |
| `fields[].type` | str | `string` \| `number` \| `timestamp` \| `enum` |
| `fields[].required` | bool | 可选，缺省 false；存在时必须为 bool |
| `fields[].enum_values` | [str] | enum 类型必须提供且非空、元素全为字符串；非 enum 类型不得出现 |

加载成功后转换为 `tuple[FieldSpec, ...]`，与内置 `SCHEMA` 完全同型。

**校验失败分类**：结构/内容非法 → `SchemaValidationError` → 参数错误（退出码 2）；文件不存在/不可读 → 运行错误（退出码 1）。

### MaskRule（脱敏规则）

冻结 dataclass，由 `--mask` 参数解析产生。

| 属性 | 类型 | 说明 |
|------|------|------|
| `pattern` | str | 非空字段名模式 |
| `mode` | str | `equal`（区分大小写精确相等）\| `contain`（不区分大小写子串包含），缺省 equal |

**匹配语义**: 记录中实际出现的每个字段名（含 schema 外字段）对全部规则做 OR 匹配；命中且值为字符串 → 掩码。

**掩码函数**: `len(v) > 4` → `v[0] + "*" * (len(v) - 2) + v[-1]`；`1 ≤ len(v) ≤ 4` → `"*" * len(v)`；空串保持空串；非字符串值原样。

### InputFormat / OutputFormat

字符串枚举 `"jsonl" | "csv"`。输入格式由 `--input-format` 显式指定或 `detect_format` 自动识别（扩展名优先 → 首非空行嗅探 → 报错）；输出格式由 `--output-format` 指定，缺省 `jsonl`。

## 变更实体

### FieldSpec / SCHEMA（schema.py）

结构不变。语义变更：`SCHEMA` 从"唯一 schema"变为"默认 schema"；管道各组件接收显式 `schema` 参数（见 research R-202）。新增派生工具：`field_names(schema)`、`timestamp_fields(schema)`。

### Record（CSV 来源）

CSV 行经表头映射 + 类型转换为 dict：

| schema 类型 | CSV 文本值转换 |
|-------------|----------------|
| number | `int` 优先、`float` 兜底；失败保留原字符串（由 validator 报 type_error） |
| string / enum / timestamp | 保持字符串（timestamp 的数字字符串由 cleaner 解析） |
| schema 外字段 | 保持字符串 |
| 空字符串单元格 | 可选字段 → 字段缺失（不进 dict）；必填字段 → 保留空串 |

### Rejection（新增来源）

结构不变。新增产生场景：CSV 行列数与表头不符 → `error_type = parse_error`，`reason = "列数不匹配: 期望 N 列, 实际 M 列"`，`record` 为该行原始文本。

### Writer（输出契约，writer.py）

| 接口 | JsonlWriter | CsvWriter |
|------|-------------|-----------|
| `write(record)` | json.dumps 追加临时文件 | 记录写临时 JSONL + 累计列首见顺序 |
| `finalize()` | 原子替换到目标 | 第二遍转 CSV（DictWriter, restval=""）→ 原子替换 → 删中间文件 |
| `abort()` | 删除临时文件 | 删除全部临时文件 |

**CSV 列序**: 全部输出记录字段名的首见顺序并集；记录缺列输出空字符串。

## 管道数据流（v2）

```
输入文件
  └─ detect_format(--input-format 或自动识别) ──识别失败──→ 运行错误退出 1
      ├─ jsonl: read_jsonl ──→ (行号, dict) | Rejection(parse_error)
      └─ csv:   read_csv(schema) ──表头非法──→ 运行错误退出 1
                └──→ (行号, dict[类型已转换]) | Rejection(parse_error: 列数不匹配)
生效 schema = load_schema(--schema) | SCHEMA ──schema 非法──→ 参数错误退出 2
  → validate(·, schema) → clean(·, schema) → dedup(按脱敏前值)
  → apply_mask(·, rules)   # 仅输出变换
  → Writer(--output-format) → 干净输出(.clean.jsonl | .clean.csv)
Rejection 全部 → 剔除明细(<输入名>.rejects.jsonl, 格式不变) + Report 计数
```

## 不变量（新增）

- 生效 schema 在整个运行中唯一且不可变；外部/内置来源对下游组件不可区分。
- 脱敏不改变 total/passed/rejected 及去重判定（对同一输入，有无 `--mask` 的报告完全一致）。
- CSV 与 JSONL 承载等价记录时，质检报告统计一致（SC-103）；输出两种格式内容等价（SC-104）。
- v1 全部既有测试不修改断言即保持通过（签名适配除外）。
