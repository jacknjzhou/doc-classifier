# 代码审查记录（任务 26）

两阶段审查：阶段一 = 规范符合性（design v1.4 逐节）；阶段二 = 代码质量（plan 全局约束 + 审查重点 6 条）。
执行日期：2026-10-09 · 基线：87 测试全绿 · 分级：Critical（必须修复）/ Major（需裁决）/ Minor（可接受/遗留）。

## 阶段一：规范符合性（design v1.4 ↔ 实现）

| design 节 | 核对结果 |
|---|---|
| 4.1 流水线 ①→⑥ | ✅ `pipeline.classify_doc` 顺序一致；summary 统计齐备 |
| 4.2 模块结构 | ✅ 全部文件就位（models/config/doc_type/normalizers/subtype/classifier/pipeline/cli/extractors×5/data×2/rules.yaml/docs） |
| 4.3 契约 | ✅ Extractor/MaterialDetector Protocol；模型 7+1（DocTypeResult）+Summary；候选合并（归一化→分组→conf=max）、路径构造、状态语义、LLM 触发/送文/重试/缓存 四条钉死全部实现并有测试 |
| 4.4 schema | ✅ version/llm/dimensions/document_types/unknown_policy 全字段入 pydantic（unknown_policy 任务 25 补入）；交叉校验（维度/材料/检测器引用、required 非空）生效 |
| 4.5 12 类 fixtures | ✅ 12 份 + 报销包 5 份 + telecom；路径/状态与 design 4.5 表一致 |
| 4.6 状态语义 + 首分节 | ✅ 并列/低于阈值→review、无候选→unknown、子类型未命中→review；首分节判定域 + 全分节材料检测 |
| §6 成功标准 1-7 | ✅ 逐条证据见 `final_report.md` |

### 规范偏差（均为 plan 简报与 design/实际 schema 的冲突，已裁决修复，全部留痕于 `.superpowers/sdd/plan/progress.md`）

**Major（改测试/接口以对齐 design，非改语义）：**
- M1 `ExtractContext` 缺 `dimension` 字段（T03 接口 vs T05 用法）→ 补字段（标签配置驱动的必需载体）
- M2 plan 测试断言中文 doc_type 名 vs design 英文 slug 键 → 测试改断言 `contract/reimbursement/…`
- M3 `Section` 缺 `title`、`index` 必填 → 字段序 `(text, title?, index?)`；`RecognizedDoc.text` 缺省由 sections 拼接
- M4 报销 `min_score: 2`（design 配置）vs 计划样例仅 1 关键词 → 修测试文本（报销人），不动 design 阈值
- M5 plan 单位模式（lookahead）匹配不了「名 数量 单位」空格形态 → 双向模式（名↔数量单位）
- M6 `normalize(value,"topic")` 双参 vs 三参签名 → 统一 `normalize(value, key, rules=None)`（key 可传维度名或策略名）
- M7 invoice_title 断言 ≥1.1 与「上限 1.0」自相矛盾 → 断言 ≥1.0-ε
- M8 topic 标签模式 `[^…]{2,30}` 无法匹配含空格的「Q4 营销方案评审会」→ 分段捕获 + 下一字段标签截止
- M9 telecom 简报数字 4=4 必并列 → 配置加 `optional:[taxi]`（5>4）+ fixture「出租车票→出租车费」规避「车票」子串
- M10 简报要求改 contract.json 会破坏 design 4.5 两段路径回归 → 新增 `contract_person.json`
- M11 `MaterialSpec` 无 `name`（yaml 材料名=键）→ load 时回填

**Critical：0 项**（无未修复的规范违背）。

## 阶段二：代码质量（plan 审查重点 6 条 + 全局约束）

| # | 失败模式 | 期望 | 核对 |
|---|---|---|---|
| 1 | 机构全/半角括号、后缀差异 | 同一 category_key | ✅ test_normalizers（括号/有限公司/分公司 三式） |
| 2 | 空文本/符号垃圾 | 不抛异常，unknown/review | ✅ test_garbage + 手工边界（空文本/空分节/纯空白 均 unknown 不崩溃） |
| 3 | LLM 超时/非法 JSON | 重试降级，文档照常 | ✅ 非法 JSON 有测试（重试 3 次→failed=1→规则结果）；**超时路径仅手工验证**（Minor-3） |
| 4 | 无分节降级 | degraded 全链路 | ✅ test_fulltext_degraded + test_nosection_degraded（subtype + 材料证据不丢） |
| 5 | 最高分并列 | review 不猜 | ✅ doc_type/subtype/classifier 三层并列测试 |
| 6 | 发票页污染 doc_type | 首分节判定 | ✅ test_no_section_uses_first_section |

全局约束：✅ 无数据库依赖（纯函数/JSON）；✅ LLM 默认关 + 全测试 mock 无网络；✅ 每结果带证据；✅ 配置驱动（扩展零代码有回归证明）；✅ 断言无弱化（全为精确路径/状态断言，无 `assert True` 式空壳）。

### Minor（可接受，列入遗留）

- Minor-1 person 默认标签集双源：`rules.yaml` labels 与 `_DEFAULT_PERSON_LABELS`（ctx.dimension 缺省时回退）——改默认标签需两处同步（rules_guide 已注明标签以配置为准）。
- Minor-2 `pipeline._section_spans` / `llm._map_span` 为近似坐标映射（find+分隔符估计），多分节文档 LLM 回写的 span 可能有 ±1 漂移——证据可追溯性不受影响（span 缺失时置 None）。
- Minor-3 LLM 超时（TimeoutError）路径无专门单测（与非法 JSON 同走 `except Exception` 降级分支，已手工验证）。
- Minor-4 `ItemExtractor.add` 条件式较绕（`value and ... or ...`），可后续重构为显式分支。
- Minor-5 材料关键词为子串匹配（`发票⊂发票号码` 属预期加分；跨材料子串需业务侧规避，rules_guide 已列已知歧义）。

**Critical：0 · Major：0（已裁决修复）· Minor：5（遗留，不阻塞交付）**
