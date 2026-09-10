# 快速开始: datalint

**日期**: 2026-09-10 | **分支**: `001-datalint-cli`

## 安装

```bash
# 在仓库根目录（需要 Python 3.10+）
pip install -e .

# 含开发依赖（pytest）
pip install -e ".[dev]"
```

## 60 秒体验

1. 准备一份脏数据 `demo.jsonl`：

```jsonl
{"id": "1", "name": "  Alice  ", "category": "A", "score": 95, "timestamp": "2026/09/10 08:00:00"}
{"id": "2", "name": "Bob", "category": "X", "timestamp": "2026-09-10T08:00:00Z"}
{"id": "3", "category": "B", "timestamp": 1789027200}
{"id": "1", "name": "Alice", "category": "A", "timestamp": "2026-09-10T09:00:00+00:00"}
not valid json
```

2. 运行：

```bash
datalint demo.jsonl --dedup-by id
```

3. 预期结果：

- `demo.clean.jsonl` — 1 条干净记录（第 1 行）：`name` 去除首尾空白为 `"Alice"`，时间戳归一为 `"2026-09-10T08:00:00Z"`。
- `demo.rejects.jsonl` — 4 条明细：第 2 行 `enum_error`（category=X 非法）、第 3 行 `missing_field`（缺必填字段 name）、第 4 行 `duplicate`（id=1 与第 1 行重复）、第 5 行 `parse_error`（非法 JSON）。
- stdout 表格报告：total=5, passed=1, rejected=4。

4. JSON 报告：

```bash
datalint demo.jsonl --dedup-by id --report-format json
```

## 运行测试

```bash
pytest
```

## 验收验证映射

| 规范验收点 | 验证方式 |
|-----------|----------|
| US1 校验剔除（P1） | `pytest tests/test_validator.py tests/test_reader.py` + 上述 demo 的 rejects 文件 |
| US2 清洗（P2） | `pytest tests/test_cleaner.py` + demo 输出中的空白/时间戳/去重表现 |
| US3 报告（P2） | `pytest tests/test_reporter.py` + 对同一输入分别跑两种 `--report-format` 比对数字 |
| SC-004 恒等式 | test_cli 端到端断言 `total == passed + rejected` |
| SC-005 性能 | 生成 10 万行文件计时（可选手动验证） |
