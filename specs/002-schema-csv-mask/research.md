# 研究: datalint v2 — 外部 schema、CSV 支持与字段脱敏

**日期**: 2026-09-10 | **分支**: `002-schema-csv-mask`

技术上下文无未解决的 NEEDS CLARIFICATION（4 项高影响决策已在规范澄清阶段确认）。以下为实现层技术决策。

## R-201: 外部 schema 加载与校验

- **Decision**: `schema.py` 新增 `load_schema(path) -> tuple[FieldSpec, ...]` 与异常 `SchemaValidationError(message)`。校验顺序：文件可读（OSError → 运行错误）→ JSON 语法 → 顶层为对象且含 `fields` 数组 → 数组非空 → 逐字段校验（name 非空字符串、不重复；type 在 `{string, number, timestamp, enum}`；required 若存在须为 bool；enum 必须携带非空 `enum_values` 且全为字符串；非 enum 不得携带 `enum_values`）。错误信息包含字段序号/名称与具体原因，一次报告首个错误（与记录校验的快速失败风格一致）。
- **Rationale**: 复用既有 `FieldSpec` 冻结 dataclass 作为内部表示，外部/内置 schema 加载后完全同型，管道零分支；首错即报使错误信息聚焦且易测。
- **Alternatives considered**: 收集全部错误一次报告（更友好但错误组合爆炸、测试面翻倍，本期不做）；JSON Schema 标准格式（需要实现解释器或第三方库，违反约束）；YAML schema（无标准库解析器，排除）。

## R-202: 管道 schema 参数化（依赖注入重构）

- **Decision**: `validate(line_no, record, schema)`、`clean(line_no, record, schema)` 显式接收 `schema: tuple[FieldSpec, ...]`；cleaner 的时间戳字段集合与 cli 的去重字段合法性均从传入 schema 派生；`schema.SCHEMA` 保留为内置默认值，cli 在启动时确定生效 schema（`--schema` 加载成功值或 `SCHEMA`）并向下传递。
- **Rationale**: 最小侵入——签名加一个参数，不引入类/上下文对象；自定义 schema 的单测无需 monkeypatch 模块常量。
- **Alternatives considered**: 全局可变 `set_active_schema()`（隐式状态、测试互相污染，违反不可变原则，排除）；将管道封装为 Pipeline 类（本期只有一个共享参数，YAGNI，排除）。

## R-203: 输入格式自动识别

- **Decision**: `reader.detect_format(path, explicit) -> "jsonl" | "csv"`：显式指定直接返回；否则扩展名 `.csv` → csv、`.jsonl`/`.json` → jsonl（不区分大小写）；其他/无扩展名时读取首个非空行嗅探——`json.loads` 成功且为对象 → jsonl；否则用 `csv.Sniffer` 失败则简单启发（含逗号且可按 CSV 解析出 ≥1 列表头）→ csv；仍无法判断抛出识别错误（运行错误，提示 `--input-format`）。嗅探只读首行后关闭，正式读取重新打开文件。
- **Rationale**: 与澄清 Q3 一致；嗅探与读取分离避免生成器状态纠缠；`csv.Sniffer` 对单列/无分隔文本会抛错，作为"无法判断"信号自然融入。
- **Alternatives considered**: 读取时边判断边处理单一文件句柄（复杂且难测，排除）；MIME/BOM 检测（超出需求，排除）。

## R-204: CSV 读取与类型转换

- **Decision**: `reader.read_csv(path, schema)` 使用 `csv.reader`（默认方言：逗号 + 双引号转义），`newline=""` 打开；首个非空行为表头，表头含空列名或重复列名 → 运行错误终止（边界情况约定）。数据行行号按物理行位置计（与 JSONL 一致，csv.reader 的 `line_num` 提供）；列数与表头不符 → `Rejection(parse_error, "列数不匹配: 期望 N 列, 实际 M 列", 原始行重组文本)`。类型转换按 schema：number 字段 `int(v)` 失败再 `float(v)`，失败保留原字符串（交给 validator 报 type_error，错误语义统一）；timestamp 字段保留字符串（cleaner 已支持数字字符串解析）；空字符串单元格对可选字段视为缺失（不进记录），对必填字段保留空串；schema 外字段保持字符串。
- **Rationale**: 转换失败"保留原值让 validator 报错"避免 reader/validator 双处报 type_error 的语义分裂；`csv.reader` 而非 `DictReader` 是为了拿到原始行列表以检测列数不匹配（DictReader 会静默塞进 `restkey`/填 None）。
- **Alternatives considered**: `csv.DictReader`（列数异常被静默吞掉，与 FR-111 要求的显式剔除冲突，排除）；在 reader 直接报 type_error（错误来源分裂，报告归类不清晰，排除）；支持自定义分隔符（超出本期范围）。

## R-205: --mask 规则解析与掩码算法

- **Decision**: 新模块 `masker.py`：
  - `parse_mask_rules(raw_list) -> tuple[MaskRule, ...]`：`raw_list` 来自 argparse `action="append"`；每项按逗号再拆分；每段格式 `pattern[:mode]`，mode ∈ {equal, contain}（缺省 equal），非法 mode 或空 pattern 抛 `ValueError`（cli 转参数错误退出 2）。
  - `MaskRule(pattern, mode)` 冻结 dataclass；`matches(field_name)`：equal 区分大小写精确相等；contain 不区分大小写子串包含。
  - `apply_mask(record, rules) -> dict`：遍历记录全部实际字段（含 schema 外），命中任一规则且值为 str 时替换：`len > 4` → `v[0] + "*"*(len-2) + v[-1]`；`len <= 4` → `"*"*len`；非字符串/未命中原样；返回新 dict。
  - 应用位置：cli 管道中 dedup 之后、写出之前（保证去重按脱敏前值判断，FR-109）。
- **Rationale**: 与澄清 Q1/Q2/Q4 逐条对应；`action="append"` + 逗号拆分同时支持重复选项与合写两种形态。
- **Alternatives considered**: 正则模式匹配（表达力过剩、用户易误伤，排除）；在 cleaner 内实现（脱敏非质检语义，且 cleaner 发生在 dedup 前会破坏 FR-109，排除）。

## R-206: 输出写出与 CSV 两遍法

- **Decision**: 新模块 `writer.py`：
  - JSONL：`JsonlWriter`——逐条 `json.dumps(ensure_ascii=False)` 流式写临时文件，成功后原子替换（复用 v1 机制）。
  - CSV：`CsvWriter`——**两遍法**。第一遍：记录流式写入临时 JSONL，同时维护列名的首见顺序列表（`dict.fromkeys` 语义并集）；第二遍：以列并集为表头，用 `csv.DictWriter(restval="", extrasaction="ignore")` 将临时 JSONL 逐行转写为临时 CSV，完成后原子替换到目标路径并删除中间 JSONL。非字符串标量值按 `json.dumps` 序列化为单元格文本（数字直接 str，None 输出空）。
  - 两种 writer 同接口（`write(record)` / `finalize()` / `abort()`），cli 按 `--output-format` 选择。
- **Rationale**: CSV 列集合需要全量记录的字段并集（假设章节：后续记录的额外字段追加在尾部），单遍流式无法回补已写行的新列；两遍法内存仍 O(列集合)，磁盘顺序读写对 10 万行规模影响可忽略（SC-005 余量大）。统一 writer 接口让 cli 对格式无感知。
- **Alternatives considered**: 全量缓冲内存后一次写出（违反内存约束，排除）；列集合固定为 schema 字段 + 首条记录额外字段、后续新字段丢弃（静默丢数据，违反 SC-104 内容等价，排除）；先扫一遍输入取列集合（输入含被剔除行，列集合含噪声且多读一遍脏数据，排除）。

## R-207: CLI 选项与兼容性

- **Decision**: 新增选项：`--schema PATH`、`--input-format {jsonl,csv}`（缺省自动识别）、`--output-format {jsonl,csv}`（缺省 jsonl）、`--mask PATTERN[:MODE][,...]`（`action="append"` 可重复）。默认输出路径按输出格式定后缀：`<输入名>.clean.jsonl` 或 `<输入名>.clean.csv`。所有新选项缺省时行为与 v1 完全一致；`--dedup-by` 字段合法性改为按生效 schema 判断。版本号升至 0.2.0。
- **Rationale**: 全部可选保证零回归（SC-107）；输出后缀跟随格式避免 `.jsonl` 文件装 CSV 内容的误导。
- **Alternatives considered**: 按 `-o` 扩展名推断输出格式（隐式行为难预期，且与显式选项冲突时语义模糊，排除）；子命令拆分（单一动作工具，YAGNI，排除）。
