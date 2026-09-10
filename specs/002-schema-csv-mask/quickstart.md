# 快速开始: datalint v2

**日期**: 2026-09-10 | **分支**: `002-schema-csv-mask`

## 前置

v1 已安装（`pip install -e ".[dev]"`）。v2 无新依赖。

## 场景 1: 自定义 schema

`my_schema.json`:

```json
{
  "fields": [
    {"name": "user_id", "type": "string", "required": true},
    {"name": "email", "type": "string", "required": true},
    {"name": "level", "type": "enum", "required": true, "enum_values": ["gold", "silver"]},
    {"name": "created_at", "type": "timestamp", "required": true}
  ]
}
```

```bash
datalint users.jsonl --schema my_schema.json --dedup-by user_id
```

预期：按 my_schema 校验（内置 schema 不生效）；`--dedup-by user_id` 合法（在新 schema 中）。

非法 schema 演练：把 `"type": "enum"` 改为 `"type": "datetime"` → 报错指明字段 `level`、非法类型 `datetime`、支持的类型列表，退出码 2，不产生输出。

## 场景 2: CSV 进、CSV 出

`users.csv`:

```csv
user_id,email,level,created_at,note
u1,  alice@example.com  ,gold,2026/09/10 08:00:00,vip
u2,bob@example.com,platinum,2026-09-10T08:00:00Z,
u3,carol@example.com,silver,1789027200
```

```bash
datalint users.csv --schema my_schema.json --output-format csv
```

预期：

- 自动识别为 CSV（扩展名）
- 第 2 行（u2）`enum_error`（platinum 非法）剔除；第 4 行（u3）列数 4 ≠ 表头 5 → `parse_error: 列数不匹配` 剔除
- `users.clean.csv` 含 1 条记录（u1）：email 去空白、created_at 归一为 `2026-09-10T08:00:00Z`
- 剔除明细仍为 `users.rejects.jsonl`（JSONL 格式）
- 报告 total=3, passed=1, rejected=2

## 场景 3: 脱敏

```bash
datalint data.jsonl --mask email:equal --mask phone:contain
```

输入记录 `{"email": "alice@example.com", "phone": "13800138000", "home_phone": "01088886666", "name": "Alice"}` 输出为：

```json
{"email": "a***************m", "phone": "1*********0", "home_phone": "0*********6", "name": "Alice"}
```

- `email` 精确命中；`phone`/`home_phone` 被 contain 模糊命中；`name` 不受影响
- 掩码长度与原值一致，保留首尾各 1 字符
- 加 `--dedup-by email` 时去重仍按真实 email 判定

## 场景 4: 兼容性回归

```bash
datalint demo.jsonl --dedup-by id
```

不带任何新选项 → 行为与 v1 完全一致（内置 schema、JSONL 进出、无脱敏）。

## 运行测试

```bash
pytest                # 全部（含 v1 回归 + v2 新增）
pytest -m "not slow"  # 跳过性能测试
```

## 验收验证映射

| 规范验收点 | 验证方式 |
|-----------|----------|
| US1 外部 schema（P1） | `pytest tests/test_schema_loading.py` + 场景 1 非法 schema 演练 |
| US2 CSV 双向（P2） | `pytest tests/test_reader.py tests/test_writer.py` + 场景 2 |
| US3 --mask（P2） | `pytest tests/test_masker.py` + 场景 3 |
| US4 不中断（P3） | 场景 2 第 4 行列数不匹配仍完成 + test_cli CSV 损坏行用例 |
| SC-103 双格式报告一致 | test_cli：同内容 JSONL/CSV 输入报告对比 |
| SC-107 零回归 | v1 全部测试保持通过 |
