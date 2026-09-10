# 任务: datalint — JSONL 数据清洗与质检 CLI

**输入**: 来自 `/specs/001-datalint-cli/` 的设计文档
**前置条件**: plan.md, spec.md, research.md, data-model.md, contracts/cli-contract.md, quickstart.md

**测试**: 规范明确要求单元测试（FR-014），采用测试先行（先写测试确认失败，再实现使其通过）。

**组织结构**: 任务按用户故事分组，每个故事可独立实施和测试。

## 格式: `[ID] [P?] [Story] 描述`

- **[P]**: 可以并行运行（不同文件，无未完成依赖）
- **[Story]**: 此任务所属用户故事（US1, US2, US3）
- 描述中包含确切文件路径

## 路径约定

单一项目 src 布局：`src/datalint/`、`tests/`（见 plan.md 项目结构）。

---

## 阶段 1: 设置(共享基础设施)

**目的**: 项目骨架与打包配置

- [X] T001 创建项目结构：`src/datalint/__init__.py`（含 `__version__ = "0.1.0"`）、空的 `tests/` 目录
- [X] T002 创建 `pyproject.toml`：setuptools backend、src 布局、`requires-python = ">=3.10"`、零运行时依赖、`[project.optional-dependencies] dev = ["pytest"]`、`[project.scripts] datalint = "datalint.cli:main"`
- [X] T003 [P] 创建 `tests/conftest.py`：共享 fixture——`write_jsonl(tmp_path, lines)` 构造临时 JSONL 输入文件、读取输出文件内容的辅助函数

---

## 阶段 2: 基础(阻塞前置条件)

**目的**: 所有故事共用的 schema 与共享类型（validator/cleaner/cli/reporter 全部依赖）

**⚠️ 关键**: 此阶段完成前无法开始任何用户故事

- [X] T004 实现 `src/datalint/schema.py`：错误类型常量（`PARSE_ERROR`/`MISSING_FIELD`/`TYPE_ERROR`/`ENUM_ERROR`/`TIMESTAMP_INVALID`/`DUPLICATE` 及 `ALL_ERROR_TYPES` 有序元组）、冻结 dataclass `FieldSpec(name, type, required, enum_values)`、内置 `SCHEMA` 常量（id/name 字符串必填、category 枚举必填 `{"A","B","C"}`、score 数字可选、timestamp 时间戳必填，见 data-model.md）、冻结 dataclass `Rejection(line, error_type, reason, record)` 及其 `to_json_line()` 序列化、`MISSING` 哨兵对象

**检查点**: 基础就绪——用户故事可以开始

---

## 阶段 3: 用户故事 1 - 校验并剔除非法记录 (优先级: P1) 🎯 MVP

**目标**: 一条命令读取 JSONL，剔除解析失败/缺必填/类型错/枚举非法的记录并写入剔除明细文件（含行号与原因），合法记录写入干净输出文件。

**独立测试**: 准备混有合法与各类非法记录的 JSONL 文件运行 CLI，验证输出文件只含合法记录、剔除明细每条附行号与原因、退出码符合契约（成功 0 / 文件错误 1）。

### 用户故事 1 的测试(先写并确认失败)⚠️

- [X] T005 [P] [US1] 在 `tests/test_reader.py` 编写 reader 单测：合法行产出 (行号, dict)（行号从 1 起）、非法 JSON 行产出 `Rejection(parse_error)` 且 `record` 为原始行文本、空白行跳过不计、JSON 非对象（数组/标量）视为 parse_error、空文件产出空流、UTF-8 中文内容正确读取
- [X] T006 [P] [US1] 在 `tests/test_validator.py` 编写 validator 单测：缺失必填字段 → `missing_field` 且原因含字段名、类型不符 → `type_error` 且原因含字段名与期望/实际类型、`bool` 值不通过 number/timestamp 类型校验、枚举非法 → `enum_error` 且原因含非法取值、schema 外未知字段不校验不剔除、合法记录原样通过、一条记录多错误只报首个（按 SCHEMA 字段声明序）
- [X] T007 [P] [US1] 在 `tests/test_cli.py` 编写 US1 端到端测试：脏输入 → 干净输出仅含合法记录（默认路径 `<input>.clean.jsonl`）、剔除明细文件每行含 line/error_type/reason/record（默认路径 `<input>.rejects.jsonl`）、成功退出码 0、输入文件不存在 → stderr 报错且退出码 1 且不产生输出文件

### 用户故事 1 的实施

- [X] T008 [P] [US1] 实现 `src/datalint/reader.py`：`read_jsonl(path) -> Iterator[tuple[int, dict] | Rejection]` 生成器——逐行流式读取（UTF-8）、`json.loads` 解析、空白行跳过、失败产出 Rejection（使 T005 通过）
- [X] T009 [P] [US1] 实现 `src/datalint/validator.py`：`validate(line_no, record) -> Rejection | None`——按 SCHEMA 顺序执行必填/类型/枚举校验，首错即返，number/timestamp 显式排除 bool，未知字段跳过（使 T006 通过）
- [X] T010 [US1] 实现 `src/datalint/cli.py` 最小管道：argparse（`INPUT`、`-o/--output`、`--rejects`，默认路径按 contracts/cli-contract.md）、编排 reader→validator、合法记录写干净 JSONL（`ensure_ascii=False`）、Rejection 写明细 JSONL、退出码 0/1、`main()` 入口（使 T007 通过；依赖 T008, T009）

**检查点**: US1 完整可独立测试——`pytest tests/test_reader.py tests/test_validator.py tests/test_cli.py` 全绿，可作为 MVP 演示

---

## 阶段 4: 用户故事 2 - 清洗合法记录 (优先级: P2)

**目标**: 通过校验的记录自动规范化——字符串去首尾空白、时间戳统一 ISO 8601 UTC（三类输入格式）、按指定字段去重保留首现。

**独立测试**: 准备含空白字符串、三种时间戳写法、重复记录的合法数据，运行 CLI 指定 `--dedup-by`，验证输出已规范化且无重复、重复计入剔除明细。

### 用户故事 2 的测试(先写并确认失败)⚠️

- [X] T011 [P] [US2] 在 `tests/test_cleaner.py` 编写 cleaner 单测：字符串字段（含 schema 外字段）去首尾空白且内部内容不变、非字符串值不动；时间戳三类输入（ISO 变体含 `Z`/`+00:00`/无时区视为 UTC、`YYYY/MM/DD HH:MM:SS`、Unix 秒级 int/float/纯数字字符串）均归一为 `YYYY-MM-DDTHH:MM:SSZ`、带非 UTC 时区正确换算、无法识别 → `Rejection(timestamp_invalid)`；去重保留首现、后续同键产出 `Rejection(duplicate)`、可选字段缺失按 MISSING 哨兵参与键比较、清洗后才去重（`" a "` 与 `"a"` 判重）、未指定去重字段不去重；清洗返回新 dict 不修改原记录

### 用户故事 2 的实施

- [X] T012 [US2] 实现 `src/datalint/cleaner.py`：`clean(record) -> dict | Rejection`（strip + `normalize_timestamp` 三段式解析，按 research.md R2 顺序：Unix 数字 → ISO → 斜杠格式）、`Deduplicator` 类（维护 `set[tuple]` 键集合，`check(record) -> Rejection | None`）（使 T011 通过；依赖 T004）
- [X] T013 [US2] 集成 cleaner 到 `src/datalint/cli.py`：管道扩展为 reader→validator→clean→dedup、新增 `--dedup-by` 选项（逗号分隔、逐个校验字段在 SCHEMA 中否则 stderr 报错退出码 2）；并在 `tests/test_cli.py` 追加 US2 端到端用例：脏时间戳输入归一化输出、`--dedup-by id` 去重、`--dedup-by 非法字段` → 退出码 2（依赖 T010, T012）

**检查点**: US1 + US2 独立运行——干净输出已规范化且无重复

---

## 阶段 5: 用户故事 3 - 生成质检报告 (优先级: P2)

**目标**: 处理结束后输出统计报告（总数/通过/剔除/六类错误计数），支持 JSON 与表格两种格式，数字一致。

**独立测试**: 对同一输入分别以 `--report-format json` 和 `table` 运行，验证两种输出统计数字一致、满足恒等式 total == passed + rejected。

### 用户故事 3 的测试(先写并确认失败)⚠️

- [X] T014 [P] [US3] 在 `tests/test_reporter.py` 编写 reporter 单测：从处理流增量累计 total/passed/rejected 与分类计数、不变量 `total == passed + rejected` 与 `rejected == sum(errors.values())`、JSON 渲染固定键序且六个错误键全部出现（含 0 值）且 `ensure_ascii=False`、表格渲染含汇总节与错误计数节且数字列右对齐、全合法输入时剔除数为 0、空输入 total=0

### 用户故事 3 的实施

- [X] T015 [US3] 实现 `src/datalint/reporter.py`：`Report` 累计器（`count_pass()`/`count_reject(error_type)`）、`render_json(report) -> str`、`render_table(report) -> str`（列宽按内容计算，格式按 contracts/cli-contract.md 报告契约）（使 T014 通过；依赖 T004）
- [X] T016 [US3] 集成 reporter 到 `src/datalint/cli.py`：管道各环节接入计数、新增 `--report-format {table,json}`（默认 table）与 `--report-file`（默认 stdout）；并在 `tests/test_cli.py` 追加 US3 端到端用例：两种格式数字一致、`--report-file` 写入文件、恒等式断言（依赖 T013, T015）

**检查点**: 三个故事全部独立可用——完整管道 = 干净输出 + 剔除明细 + 双格式报告

---

## 阶段 6: 完善与横切关注点

**目的**: 入口补全、文档、边界用例与验收验证

- [X] T017 [P] 创建 `src/datalint/__main__.py`：`from datalint.cli import main; main()` 支持 `python -m datalint`（依赖 T010）
- [X] T018 [P] 编写 `README.md`：项目简介、安装（`pip install -e ".[dev]"`）、内置 schema 说明、CLI 用法与选项表、quickstart demo 示例（输入/输出/报告样例）、运行测试说明（内容对齐 specs/001-datalint-cli/quickstart.md 与 cli-contract.md）
- [X] T019 在 `tests/test_cli.py` 追加边界用例：空输入文件（0 行）→ 正常完成 total=0 退出码 0、全部记录非法 → 空干净输出 + 全量明细 + 退出码 0、含空白行输入不计入 total、`python -m datalint` 调用等效（依赖 T016, T017）
- [X] T020 [P] 性能验证（SC-005）：编写 `tests/test_performance.py`（标记 `@pytest.mark.slow`）——生成 10 万行混合输入，断言处理完成时间 < 60 秒
- [X] T021 最终验收：完整运行 `pytest`（全绿）、按 specs/001-datalint-cli/quickstart.md 执行 demo 并核对预期结果（1 条干净记录、4 条明细、total=5/passed=1/rejected=4）、核对 CLI 行为与 contracts/cli-contract.md 逐项一致（依赖 T017–T020）

---

## 依赖关系与执行顺序

### 阶段依赖关系

- **设置(阶段 1)**: 无依赖，可立即开始
- **基础(阶段 2)**: 依赖 T001；阻塞所有用户故事
- **用户故事(阶段 3–5)**: 均依赖 T004（schema/共享类型）
  - US1 无其他故事依赖（MVP）
  - US2 的 T013、US3 的 T016 修改 `cli.py`，与 US1 的 T010 存在文件依赖：**T010 → T013 → T016 必须顺序执行**
  - US2/US3 的模块与测试（T011/T012、T014/T015）互相独立，可并行
- **完善(阶段 6)**: T017/T018/T020 可在依赖满足后并行；T021 最后执行

### 关键路径

```
T001 → T004 → T010 → T013 → T016 → T019 → T021
```

### 并行机会

- 阶段 1: T003 与 T002 并行
- 阶段 3: T005/T006/T007 三个测试文件并行；随后 T008/T009 并行
- 跨故事: T004 完成后，US2 的 T011→T012 与 US3 的 T014→T015 可与 US1 并行推进（仅 cli 集成任务需排队）
- 阶段 6: T017/T018/T020 并行

---

## 并行示例: 用户故事 1

```bash
# 一起启动 US1 的全部测试编写（确认失败后再实现）:
任务: "在 tests/test_reader.py 编写 reader 单测"
任务: "在 tests/test_validator.py 编写 validator 单测"
任务: "在 tests/test_cli.py 编写 US1 端到端测试"

# 测试就绪后并行实现两个独立模块:
任务: "实现 src/datalint/reader.py"
任务: "实现 src/datalint/validator.py"

# 最后串行完成编排:
任务: "实现 src/datalint/cli.py 最小管道"
```

---

## 实施策略

### 仅 MVP(用户故事 1)

1. 完成阶段 1（T001–T003）+ 阶段 2（T004）
2. 完成阶段 3（T005–T010）
3. **停止并验证**: 运行 US1 独立测试——脏数据进、干净数据 + 剔除明细出
4. 此时已是可演示的过滤器工具

### 增量交付

1. 设置 + 基础 → 骨架就绪
2. + US1 → MVP：校验与剔除（可演示）
3. + US2 → 清洗：规范化 + 去重（可演示）
4. + US3 → 报告：完整质检工具（可演示）
5. + 阶段 6 → README、边界、性能验证、最终验收

---

## 注意事项

- [P] 任务 = 不同文件且无未完成依赖
- `cli.py` 被 T010/T013/T016 依次修改，是唯一的跨故事串行点
- 每个测试任务先写并运行确认失败（RED），对应实现任务使其通过（GREEN）
- 每个任务或逻辑组完成后提交（提交格式见 git-workflow 规则：`feat:`/`test:`/`docs:`）
- 在任一检查点可停下独立验证该故事
