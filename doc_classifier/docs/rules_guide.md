# rules.yaml 编写指南

本指南与 `doc_classifier/config.py` 的 pydantic schema 一一对应（字段名即 schema 字段名）。
配置加载时做交叉校验（维度引用、材料引用、检测器注册、required 非空），**写错会直接抛错**，不会静默生效。

## 顶层结构

```yaml
version: "1.3"        # 字符串（保持引号：pydantic 按 str 校验）
llm: {...}            # LLM 兜底总配置
dimensions: {...}     # 维度定义（可复用的抽取策略单元）
document_types: {...} # 文档类型（判定 + 维度组合 + 可选子类型层）
unknown_policy: { status: review, dimension: none }   # 无法分类的去向（v1 固定 review）
```

## `llm` 块

| 字段 | 默认 | 说明 |
|---|---|---|
| `enabled` | `false` | 主开关。env `DOC_CLASSIFIER_LLM=off` 优先级最高，可强制关闭 |
| `base_url` | `""` | OpenAI 兼容网关地址（可指向内网模型） |
| `api_key_env` | `OPENAI_API_KEY` | 从该环境变量读 key（key 不写进文件） |
| `model` | `""` | 模型名；空 = `gpt-4o-mini` |
| `timeout_sec` | `20` | 单次调用超时 |
| `max_retries` | `2` | 超时/5xx/JSON 解析失败的重试次数；耗尽 → 降级为规则结果并计 `summary.llm_failed` |

**触发策略（引擎钉死，不可配）**：主维度（priority 最小）规则后未达阈值才调用；每文档一次调用所有待补维度；同文同字段内存缓存。

## `dimensions`（维度）

| 字段 | 说明 |
|---|---|
| `extractor` | 已注册的抽取器名：`party_a` / `person` / `item` / `department` / `topic` / `invoice_title` / `llm` |
| `normalize` | 归一化策略名：`org` / `person` / `item` / `topic` / `invoice_title`（空 = 恒等） |
| `llm_fallback` | `true` 时该维度可被 LLM 兜底补全 |
| `threshold` | 通过阈值：维度终值 conf ≥ 该值才算"通过" |
| `labels` | **字段标签集（配置驱动）**：规则抽取器按集合匹配，如 `报销人：张三` → person_name。改标签集 = 改这一行 |

内置抽取器的置信度口径（`source: "rule"`）：

| 抽取器 | 策略 |
|---|---|
| `person` | 标签邻接 0.9 · 称谓邻接（经理/总监…）0.8 · 姓氏表独立 2-3 字中文串：3 字 0.6 / **2 字 0.4（低于 0.6 阈值，永不单独通过）** |
| `party_a` | 标签（甲方/甲方名称）冒号取值 0.9 |
| `item` | 标签（品名/货物名称/物料）0.9 · 名称×数量单位模式 0.7 |
| `department` | 标签（部门/所在部门/发文单位/发文部门，左边界防"各部门"子串误命中）0.9 · 组织后缀（部/中心/科…）+词表校验 0.7，含包含去重 |
| `topic` | 标签（会议主题/议题，按下一字段标签截止）0.9 · `关于…的会议纪要` 0.7 · 首行回退 0.5 |
| `invoice_title` | 购方标签 0.9；命中行 ±3 行内出现 18 位统一社会信用代码 → +0.2（上限 1.0）。**不匹配裸"名称："** |
| `llm` | 兜底：模型自报 confidence |

## `document_types`（文档类型）

| 字段 | 说明 |
|---|---|
| `display` | 展示名（`category_path` 第一段用它） |
| `detect.keywords` | 判定关键词。**计分 = distinct 命中数**（同一词出现多次计一次；有分节时只数**第一个分节**，标题命中额外 +1） |
| `detect.min_score` | 达标阈值（默认 1）。最高分 < 自身 min_score 时不判中 |
| `dimensions` | 使用的维度 + `priority`（越小越优先；**主维度 = 通过的维度中 priority 最小者**） |
| `subtypes` | 可选子类型层（见下）；**无此段 = 不启用，零开销** |

判定结果：唯一最高且达标 → `classified`；**并列 → `review`（不猜）**；无命中 → `unknown`。

### `subtypes`（子类型层，v1 仅报销启用）

```yaml
subtypes:
  materials:                 # 材料定义（全配置化）
    invoice: { display: 发票, keywords: [发票, 发票号码, 价税合计] }
    # 可选: detector: <注册名>（默认 keyword；自定义检测器实现 MaterialDetector Protocol）
  options:                   # 报销类型
    travel_expense:
      display: 差旅费报销
      required: [invoice, itinerary]     # 必需材料：缺一 → 该 option 无候选资格
      optional: [hotel, taxi]
      weight_required: 2.0               # 默认 2
      weight_optional: 1.0               # 默认 1
      dimensions: [{use: person_name, priority: 1}]   # 可选：覆盖 doc_type 默认维度
```

判定（①c）：`required` 全命中才有资格；计分 = `required 命中数 × weight_required + optional 命中数 × weight_optional`；**唯一最高分胜出；并列/无候选 → 最终 `status = "review"`（即使维度候选存在也不自动归档）**。

## 扩展清单（各一步，零代码改动）

1. **新文档类型**：`document_types` 加一段（`display` + `detect` + `dimensions` 引用已有维度）。
2. **新报销类型**：`reimbursement.subtypes.options` 加一段（required/optional/权重/维度覆盖）。
3. **新材料**：`reimbursement.subtypes.materials` 加一行（display + keywords，可选 detector）。
4. **新字段标签**：`dimensions.<维度>.labels` 加词（如 person 加 `经办人`）。
5. **换主维度**：`document_types.<类型>.dimensions` 调整 `priority`（`tests/fixtures/rules_alt.yaml` 有完整示例）。

## 已知歧义与逃生口

- **发票抬头购/销方**：内置只取购方（`购方名称/购买方名称` 标签 + 税号邻位校验）。需要销方/开票方时，在 `invoice_title.labels` 增标签或新增维度——注意购方通常与税号同页，销方无此校验，置信度口径自行权衡。
- **单页报销单**：材料只有审批单（无发票）时所有 option 的 required 不全 → `review`。若业务上单页报销单也需直接按人归档，加一个轻量 option（如 `one_page: {display: 单页报销, required: [approval]}`）即可——**配置即解决**。
- **2 字人名**：无标签/称谓邻接的独立 2 字名置信度 0.4（< 0.6 阈值）→ 不通过；需 LLM 兜底或标签邻接才能归档。3 字名 0.6 可单独通过（姓氏表命中）。
- **材料关键词子串**：材料检测是子串匹配（`发票` ⊂ `发票号码` 会同时命中两词，属预期加分）；但 `车票` ⊂ `出租车票` 这类跨材料子串需业务侧在 keywords 里规避（见 telecom 样例用 `出租车费`）。

## 扩展方向（预留）

- 新 extractor/normalizer：实现 `Extractor` / `MaterialDetector` Protocol + `register_*`，配置引用（引擎不硬编码业务词）。
- 日期 / 项目编号 / 资产编号等结构化维度：按 `dimensions` 同构扩展（extractor 名自定义注册）。
- 持久化：引擎无状态，`classify_doc` 可被任意存储层调用。
