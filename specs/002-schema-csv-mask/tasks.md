# 任务: datalint v2 — 外部 schema、CSV 支持与字段脱敏

**输入**: 来自 `/specs/002-schema-csv-mask/` 的设计文档
**前置条件**: plan.md, spec.md, research.md, data-model.md, contracts/cli-contract.md, quickstart.md

**测试**: FR-112 显式要求单元测试覆盖异常分支，延续测试先行（先写测试确认失败，再实现使其通过）。v1 全部测试作为回归门（SC-107），任何任务完成后 v1 用例必须保持通过。

**组织结构**: 任务按用户故事分组，每个故事可独立实施和测试。

## 格式: `[ID] [P?] [Story] 描述`

- **[P]**: 可以并行运行（不同文件，无未完成依赖）
- **[Story]**: 此任务所属用户故事（US1~US4）
- 描述中包含确切文件路径

## 路径约定

单一项目 src 布局：`src/datalint/`、`tests/`（见 plan.md 项目结构）。

---

## 阶段 1: 设置

**目的**: 版本与测试基础设施

- [X] T001 版本升级与测试 fixture：`pyproject.toml` 与 `src/datalint/__init__.py` 版本改为 `0.2.0`；`tests/conftest.py` 新增 `write_csv(tmp_path, header, rows)`（构造临时 CSV 文件，支持原始行字符串以构造列数不匹配）与 `write_schema(tmp_path, obj)`（构造临时 schema JSON 文件，支持写入非法 JSON 原文）fixture

---

## 阶段 2: 基础(阻塞前置条件)

**目的**: 管道 schema 参数化重构（research R-202）——US1 的直接前提，US2 的 CSV 类型转换与 US3 均在其上运行

**⚠️ 关键**: 此阶段完成前无法开始任何用户故事

- [X] T002 schema 参数化重构：`src/datalint/schema.py` 新增派生助手 `field_names(schema)` 与 `timestamp_fields(schema)`；`src/datalint/validator.py` 的 `validate` 改签名为 `validate(line_no, record, schema)`（内部遍历传入 schema）；`src/datalint/cleaner.py` 的 `clean` 改签名为 `clean(line_no, record, schema)`（时间戳字段从传入 schema 派生，删除模块级 `_TIMESTAMP_FIELDS`）；`src/datalint/cli.py` 确定生效 schema（暂为 `SCHEMA`）并传入 `_process` 与 `_parse_dedup_fields`；适配 `tests/test_validator.py` 与 `tests/test_cleaner.py` 的调用签名。**验收: 全量 v1 测试（71 项）保持通过，无断言修改**

**检查点**: 管道对 schema 来源无感知——用户故事可以开始

---

## 阶段 3: 用户故事 1 - 从外部 JSON 文件加载 schema (优先级: P1) 🎯 MVP

**目标**: `--schema` 指定外部 JSON schema 文件，加载前完整自校验，非法 schema 给出指明字段与原因的报错且不产生输出；合法 schema 完全替代内置 schema。

**独立测试**: 用自定义 schema 文件运行验证新规则生效；构造 10 类非法 schema 验证各得明确报错与正确退出码。

### 用户故事 1 的测试(先写并确认失败)⚠️

- [X] T003 [P] [US1] 新建 `tests/test_schema_loading.py`：合法 schema 加载为与内置同型的 FieldSpec 元组（required 缺省 false）；逐类非法 schema 断言 `SchemaValidationError` 且错误信息含定位内容——JSON 语法错误、顶层非对象、缺 `fields`、`fields` 非数组、`fields` 为空、字段缺 name/name 为空/name 非字符串、name 重复、type 缺失或不在支持集合（错误信息列出支持的类型）、required 非 bool、enum 缺 `enum_values`/为空/含非字符串、非 enum 携带 `enum_values`；文件不存在抛 OSError 类异常
- [X] T004 [P] [US1] 在 `tests/test_cli.py` 追加 US1 端到端用例：`--schema` 合法文件 → 数据按新 schema 校验（内置 schema 字段不再要求）、`--dedup-by` 按生效 schema 判合法性；schema 内容非法 → stderr 含字段定位信息、退出码 2、不产生 clean/rejects 文件；schema 文件不存在 → 退出码 1、不产生输出；不带 `--schema` → 行为与 v1 一致（回归）

### 用户故事 1 的实施

- [X] T005 [US1] 在 `src/datalint/schema.py` 实现 `SchemaValidationError(ValueError)` 与 `load_schema(path) -> tuple[FieldSpec, ...]`：按 research R-201 的校验顺序逐项检查，首错即抛，错误信息含字段序号/名称与原因（使 T003 通过；依赖 T002）
- [X] T006 [US1] 在 `src/datalint/cli.py` 集成 `--schema PATH` 选项：启动时加载（OSError → stderr + 退出码 1；SchemaValidationError → stderr + 退出码 2，均不产生输出文件），生效 schema 注入管道与 `--dedup-by` 校验（使 T004 通过；依赖 T005）

**检查点**: US1 完整可独立测试——自定义 schema 驱动全管道，非法 schema 明确报错

---

## 阶段 4: 用户故事 2 - CSV 输入与可选输出格式 (优先级: P2)

**目标**: CSV 输入自动识别（扩展名优先 + 内容嗅探）并按 schema 类型转换；输出格式可选 JSONL（默认）/CSV（两遍法，列集合首见顺序并集）。

**独立测试**: CSV 文件（含损坏行）完整走通管道；同内容 JSONL/CSV 输入报告一致；两种输出格式内容等价。

### 用户故事 2 的测试(先写并确认失败)⚠️

- [X] T007 [P] [US2] 在 `tests/test_reader.py` 追加格式识别与 CSV 读取单测：`detect_format`——显式指定直返、`.csv`/`.jsonl`/`.json` 扩展名识别（不区分大小写）、无扩展名嗅探（JSON 对象行 → jsonl、CSV 表头 → csv）、空文件/无法判断抛识别错误；`read_csv(path, schema)`——表头映射、行号按物理行、number 字段 int/float 转换、转换失败保留原字符串、timestamp 字段保持字符串、schema 外字段保持字符串、空单元格（可选字段缺失/必填字段保留空串）、列数不匹配产出 `Rejection(parse_error)` 且 reason 含期望/实际列数、表头空列名或重复列名抛错、只有表头产出空流
- [X] T008 [P] [US2] 新建 `tests/test_writer.py`：JsonlWriter——write/finalize 后目标文件内容正确、abort 后无遗留文件；CsvWriter——两遍法产出带表头 CSV、列集合为全部记录字段首见顺序并集、后续记录新字段追加列尾、记录缺列输出空字符串、非字符串标量正确序列化（数字/None）、含逗号与引号的值正确转义、abort 清理全部临时文件、finalize 后无 `.tmp` 中间文件残留

### 用户故事 2 的实施

- [X] T009 [P] [US2] 在 `src/datalint/reader.py` 实现 `detect_format(path, explicit)` 与 `read_csv(path, schema)`：按 research R-203/R-204——csv.reader、`newline=""`、类型转换失败留给 validator、列数校验（使 T007 通过；依赖 T002）
- [X] T010 [P] [US2] 新建 `src/datalint/writer.py`：统一接口 `write(record)`/`finalize()`/`abort()`；`JsonlWriter`（从 cli 现有写出逻辑抽取，含临时文件 + 原子替换）与 `CsvWriter`（两遍法：临时 JSONL + 列首见顺序累计 → csv.DictWriter(restval="", extrasaction="ignore") 转写 → 原子替换 → 清理中间文件）（使 T008 通过）
- [X] T011 [US2] 在 `src/datalint/cli.py` 集成：新增 `--input-format {jsonl,csv}` 与 `--output-format {jsonl,csv}` 选项；输入经 `detect_format` 分派 `read_jsonl`/`read_csv`（识别失败/表头非法 → stderr + 退出码 1）；输出改用 writer 接口，默认输出路径后缀随格式（`.clean.jsonl`/`.clean.csv`）；并在 `tests/test_cli.py` 追加 US2 端到端用例——CSV 进 JSONL 出、CSV 进 CSV 出（表格工具可读断言：csv 模块回读）、同内容 JSONL/CSV 输入报告数字一致（SC-103）、两种输出格式记录内容等价（SC-104）、无法识别格式退出码 1 且提示 `--input-format`、`.csv` 文件缺省识别（使全部通过；依赖 T006, T009, T010）

**检查点**: US1 + US2 独立运行——任意 schema × 任意格式进出

---

## 阶段 5: 用户故事 3 - --mask 字段脱敏 (优先级: P2)

**目标**: `--mask PATTERN[:MODE]`（可重复/逗号合写，equal 默认/contain 混用）对记录全部实际字段做首尾保留掩码，仅影响输出不影响质检语义。

**独立测试**: 混合模式脱敏验证命中范围差异；`--dedup-by` 被脱敏字段仍按真实值去重；有无 `--mask` 报告一致。

### 用户故事 3 的测试(先写并确认失败)⚠️

- [X] T012 [P] [US3] 新建 `tests/test_masker.py`：`parse_mask_rules`——单模式默认 equal、`pattern:contain` 解析、重复选项与逗号合写合并、非法 mode 抛 ValueError（含模式名）、空 pattern（`,`/`:equal`/空串）抛 ValueError；`MaskRule.matches`——equal 区分大小写精确相等、contain 不区分大小写子串（`phone` 命中 `home_phone`/`PhoneNumber`）；`apply_mask`——长度 >4 保留首尾各 1 中间等长 `*`、长度 1–4 全 `*`、空串不变、非字符串值原样、未命中字段原样、schema 外字段参与匹配、返回新 dict 不修改原记录

### 用户故事 3 的实施

- [X] T013 [US3] 新建 `src/datalint/masker.py`：冻结 dataclass `MaskRule(pattern, mode)` 与 `matches(field_name)`、`parse_mask_rules(raw_list)`、`apply_mask(record, rules)`（按 research R-205 与 data-model 掩码函数）（使 T012 通过）
- [X] T014 [US3] 在 `src/datalint/cli.py` 集成 `--mask`（`action="append"`）：解析失败 → 参数错误退出码 2；应用位置在 dedup 之后、writer.write 之前；并在 `tests/test_cli.py` 追加 US3 端到端用例——混合模式命中差异、被 mask 字段的 `--dedup-by` 仍按真实值判重、有无 `--mask` 报告统计一致、原始值在干净输出中出现 0 次（SC-105）、CSV 输出同样生效、非法 mode 退出码 2（使全部通过；依赖 T011, T013）

**检查点**: 三个故事组合可用——自定义 schema × CSV × 脱敏任意组合

---

## 阶段 6: 用户故事 4 - 不可解析行的持续处理 (优先级: P3)

**目标**: 任何单行解析失败（JSONL/CSV）不中断处理，损坏行全部进入剔除明细，处理以成功状态完成。

**独立测试**: 全损坏与混合损坏的 JSONL/CSV 文件均完整处理并退出 0。

### 用户故事 4 的实施(验证性)

- [X] T015 [US4] 在 `tests/test_cli.py` 追加持续处理端到端用例：CSV 混合损坏行（列数不匹配 + 类型转换失败 + 枚举非法）→ 处理完成退出 0、损坏行全部在剔除明细中且附行号与原因；CSV 全部行损坏 → 空干净输出 + 全量明细 + 退出 0；JSONL 损坏行行为回归（与 v1 一致）；确认无任何单行错误会抛出未捕获异常（依赖 T011）

**检查点**: 全部故事完成——损坏输入的鲁棒性经端到端验证

---

## 阶段 7: 完善与横切关注点

**目的**: 文档、最终验收

- [X] T016 [P] 更新 `README.md`：新选项表（--schema/--input-format/--output-format/--mask）、外部 schema 文件格式说明与示例、CSV 进出示例、脱敏示例（混合模式）、退出码新增场景（对齐 specs/002-schema-csv-mask/contracts/cli-contract.md 与 quickstart.md）
- [X] T017 最终验收：完整运行 `pytest`（v1 71 项 + v2 新增全绿，SC-107）、按 specs/002-schema-csv-mask/quickstart.md 实际演练 4 个场景并核对预期、逐项核对 contracts/cli-contract.md 行为契约（依赖 T014, T015, T016）

---

## 阶段 8: Bugfix (2026-09-11)

**Bugfix**: 2026-09-11 — [BUG-001~006] Updated from bugfix patch

**目的**: 修复验收后报告的 6 个缺陷（明细见 `bugs/BUG-001.md` ~ `bugs/BUG-006.md`），测试先行

- [X] T018 [BUG-001] 时间戳保留亚秒精度：`src/datalint/cleaner.py` 的 `normalize_timestamp` 微秒非零时输出 `.ffffff`（去尾零），微秒为零维持秒级；在 `tests/test_cleaner.py` 补测试（`.123Z` 与 `.456Z` 不再归一相同、`--dedup-by timestamp` 不误杀、尾零剥离、Unix 浮点小数保留）
- [X] T019 [BUG-002] 剥离 UTF-8 BOM：`src/datalint/reader.py`（read_jsonl/read_csv/detect_format 嗅探）与 `src/datalint/schema.py`（load_schema）读取改用 `encoding="utf-8-sig"`；在 `tests/test_reader.py`/`tests/test_cli.py` 补带 BOM 的 JSONL 与 CSV 端到端测试
- [X] T020 [BUG-003] 去重字段缺失跳过去重：`src/datalint/cleaner.py` 的 `Deduplicator.check` 键含 MISSING 时直接返回 None（不判重不注册）；更新 `tests/test_cleaner.py::test_dedup_missing_optional_field_uses_sentinel` 为新语义并补多缺失记录全保留用例
- [X] T021 [BUG-004] naive 时间戳告警：`src/datalint/cleaner.py` 的 `clean` 接收可选统计对象累计"按 UTC 假定"次数，`src/datalint/cli.py` 处理结束后向 stderr 输出一次汇总警告（不影响退出码/报告）；在 `tests/test_cli.py` 补断言 stderr 警告与报告数字不变
- [X] T022 [BUG-005] 默认路径基底规则：`src/datalint/cli.py` 的 `_default_path` 仅剥离 `.jsonl`/`.json` 扩展名，其余保留完整文件名；更新 `tests/test_cli.py` 中 CSV 输入的默认路径断言并补 `a.jsonl`/`a.csv` 互不覆盖用例
- [X] T023 [BUG-006] 可选字段 nullable：`src/datalint/validator.py` 可选字段值为 None 时跳过类型/枚举校验，`src/datalint/cleaner.py` 时间戳字段值为 None 时跳过归一；必填字段 null 仍 type_error；在 `tests/test_validator.py`/`tests/test_cleaner.py`/`tests/test_cli.py` 补正反用例（JSONL 输出保留 null）
- [X] T024 Bugfix 回归验收：全量 `pytest` 通过、`/speckit.bugfix.verify` 一致性检查通过、README 假设章节与实现同步（依赖 T018–T023）

---

## 依赖关系与执行顺序

### 阶段依赖关系

- **设置(阶段 1)**: 无依赖
- **基础(阶段 2)**: 依赖 T001；T002 重构阻塞所有故事
- **用户故事(阶段 3–6)**:
  - US1（T003–T006）: 依赖 T002
  - US2（T007–T011）: 模块任务（T007–T010）仅依赖 T002，可与 US1 并行；**T011 依赖 T006**（cli.py 串行链）
  - US3（T012–T014）: T012/T013 仅依赖 T001，可提前并行；**T014 依赖 T011 + T013**
  - US4（T015）: 依赖 T011
- **完善(阶段 7)**: T016 随时可做（内容对齐契约）；T017 最后

### 关键路径

```
T001 → T002 → T005 → T006 → T011 → T014 → T017
                              └→ T015 ──────┘
```

`cli.py` 由 T006 → T011 → T014 依次修改；`tests/test_cli.py` 由 T004 → T011 → T014 → T015 依次追加——两条串行链重合。

### 并行机会

- 阶段 3–5 的测试编写：T003/T004/T007/T008/T012 五个测试任务在 T002 后可全部并行
- 模块实现：T005（schema）、T009（reader）、T010（writer）、T013（masker）四个不同文件在各自测试就绪后可并行
- 阶段 7: T016 与开发并行

---

## 并行示例: 基础完成后的最大并行度

```bash
# T002 完成后, 一起启动全部故事的测试编写:
任务: "新建 tests/test_schema_loading.py"         (T003)
任务: "test_cli.py 追加 US1 端到端用例"           (T004)
任务: "test_reader.py 追加格式识别与 CSV 单测"    (T007)
任务: "新建 tests/test_writer.py"                 (T008)
任务: "新建 tests/test_masker.py"                 (T012)

# 测试就绪(RED)后并行实现四个独立模块:
任务: "schema.py 实现 load_schema"                (T005)
任务: "reader.py 实现 detect_format + read_csv"   (T009)
任务: "新建 writer.py"                            (T010)
任务: "新建 masker.py"                            (T013)

# cli 集成必须串行: T006 → T011 → T014
```

---

## 实施策略

### 仅 MVP(用户故事 1)

1. 阶段 1（T001）+ 阶段 2（T002，v1 测试保持绿）
2. 阶段 3（T003–T006）
3. **停止并验证**: 自定义 schema 驱动全管道，10 类非法 schema 明确报错
4. 此时工具已可适配任意结构的 JSONL 数据集

### 增量交付

1. 设置 + 基础重构 → 管道 schema 无关化（v1 行为不变）
2. + US1 → 外部 schema（可演示：自定义数据集质检）
3. + US2 → CSV 双向（可演示：CSV 进 CSV 出）
4. + US3 → 脱敏（可演示：合规交付）
5. + US4 验证 + 阶段 7 → README、最终验收

---

## 注意事项

- [P] 任务 = 不同文件且无未完成依赖
- `cli.py`（T006→T011→T014）与 `tests/test_cli.py`（T004→T011→T014→T015）是仅有的串行链
- 每个测试任务先写并运行确认失败（RED），对应实现任务使其通过（GREEN）
- **每个任务完成后必须全量跑 v1 测试确认零回归（SC-107）**
- 每个任务或逻辑组完成后提交（`feat:`/`test:`/`refactor:`/`docs:`）
