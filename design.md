# 文档分类引擎（维度涌现式）：设计文档

> Superpowers 阶段 1-2 产出 · 版本 **v1.4** · 状态：待评审
> v1.4 修订要点：输入增加 `sections` 分节模型、统一 `category_path` 构造规则、钉死 LLM 调用/候选合并/doc_type 平局三组决策、字段标签配置化、`subtypes` 移入 doc_type 字段、LLM 顶层开关（默认关闭）。完整清单见 §8。

---

## 1. 问题陈述

**一句话**：现有文档分类是"文档 → 固定类别"，而本需求要求 **"文档 → 先识别内容，再依据识别出的关键词所属维度（人名 / 物品 / 甲方名称 …）动态决定分类方式"**——分类维度本身是涌现的、可配置的。

**与传统分类的本质区别**：

| 维度 | 传统分类 | 本需求（维度涌现式） |
|---|---|---|
| 分类依据 | 文档整体特征（主题、模板、关键词密度） | **抽取出的实体关键词**（人名/物品/甲方名） |
| 类别空间 | 预定义、固定枚举 | **由抽取结果动态决定**，可能无限增长 |
| 谁来定类别 | 训练时确定 | **运行时由 rules.yaml 决定**用哪个维度 |
| 同类文档 | 归同一类 | 同一类文档可能按不同维度分（合同按甲方名、简历按人名） |

**它要解决的真实问题**：文档集中归档时，业务上希望"同一份合同都归到甲方公司名下""同一人的材料都归到这个人名下""同类物品的凭证归到一起"，而不同文档该按哪个维度归档，取决于它是什么类型的文档。

---

## 2. 目标用户与使用场景

- **直接使用者（机器）**：现有文档识别流水线的后置处理模块（用户已确认集成形态）。
- **间接使用者（人）**：档案管理员 / 合同专员 / 人事，消费归档结果做检索与复核。
- **核心场景**：识别后的文本或结构化 JSON 进入引擎 → 输出"该文档属于哪个维度、归属键是什么、证据在哪"。

---

## 3. 设计方案（3 方案对比）

### 方案 A：纯规则 / 词典 / 正则引擎
- **优点**：零模型依赖、完全离线、可解释、可单测、延迟极低。
- **缺点**：人名变体（曾用名/别名）、自由表述的物品名召回有限；词典需人工冷启动维护。
- **复杂度**：低。

### 方案 B：纯 LLM 结构化抽取
- **优点**：召回高、自由文本适应性强、开发最快。
- **缺点**：成本与延迟高（每篇一次调用）、输出不稳定需校验重试、隐私合规风险（全文出网）、离线不可用。
- **复杂度**：中。

### 方案 C（推荐）：混合「规则优先 + LLM 兜底 + 配置驱动维度」
- **做法**：先用正则/实体词典/领域词表快速命中；命中置信度不足或未命中时，才把该文档（或片段）交给 LLM 按 JSON schema 结构化抽取；两者结果合并打分。**用哪个维度、什么时候兜底，全部写在 `rules.yaml` 里**。
- **优点**：成本/延迟可控（多数文档走规则）、可解释（保留证据 span）、召回足够、契合"嵌入识别流水线"的轻量定位、规则改动不改代码。
- **缺点**：两套抽取器需统一契约；需要归一化/消歧模块。
- **复杂度**：中。

### ✅ 推荐方案：C
**理由**：本需求的核心价值是"**维度可配置 + 分类键要准**"，而不是"抽取要炫"。规则层保证稳定与可解释，LLM 层只负责补规则覆盖不到的长尾，成本与合规风险都在可控边界内；且配置文件驱动的形态天然贴合"嵌入流水线后置模块"的定位。

---

## 4. 技术架构

### 4.1 处理流水线（7 段）

```
[识别流水线输出]
   │  RecognizedDoc{ doc_id, text, sections?, structured?, source }
   ▼
①  文档类型判定 doc_type        ── 关键词 distinct 计分（判定文本 = 首分节；无分节 = 全文）；多命中取高分；并列 → review
   ▼
①b 材料检测 materials           ── KeywordMaterialDetector 按页/分节（仅配置了 subtypes 的 doc_type）
   ▼
①c 子类型判定 subtype           ── required 门控 + 计分；唯一最优 → 命中；并列或无候选 → review（不猜）
   ▼
②  维度选择 dimension           ── rules.yaml 中该 doc_type 声明的维度（按 priority；subtype 可覆盖）
   ▼
③  实体抽取 extract             ── L1 规则抽取器；未达阈值的维度触发一次 LLM 调用（主开关开启时）
   ▼
④  归一化/消歧 normalize        ── org / person / item / topic 统一形态，生成 category_key
   ▼
⑤  分类决策 classify            ── 候选合并、阈值过滤、主维度选取、status
   ▼
⑥  输出 Classification + summary ── { doc_type, subtype, dimension, category_path, confidence, evidence[] }
   │
   └─▶ 归档标签 / 目录名 / 入库字段 / 人工复核队列（review/unknown）/ 命中率统计
```

### 4.2 模块结构（Python 包）

```
doc_classifier/
├── __init__.py
├── models.py            # RecognizedDoc / Section / Candidate / Evidence / MaterialHit / SubtypeResult / Classification
├── config.py            # 加载并校验 rules.yaml（pydantic）：DimensionSpec / DocTypeSpec / SubtypesSpec / LLMConfig
├── doc_type.py          # ① 文档类型判定器
├── extractors/
│   ├── base.py          # Extractor / MaterialDetector 协议 + ExtractContext + 注册表
│   ├── rule.py          # L1 规则抽取器：party_a / person / item / department / topic / invoice_title
│   ├── llm.py           # L2 LLM 兜底抽取器（OpenAI 兼容，每文档一次调用，重试+降级，内存缓存）
│   ├── material.py      # ①b 通用材料检测器 KeywordMaterialDetector（材料全配置化，引擎零硬编码）
│   └── registry.py      # 抽取器/检测器注册表（按名字取用，供 rules.yaml 引用）
├── normalizers.py       # ④ 归一化：org / person / item / topic
├── subtype.py           # ①c 子类型判定器（材料组合 → 子类型）
├── classifier.py        # ⑤ 分类决策与冲突消解
├── pipeline.py          # 编排 ①→⑥（含 ①b/①c）+ summary 统计
├── cli.py               # 命令行入口（JSONL 进出 + summary 输出）
├── rules.yaml           # 默认规则（v1.3 schema；CLI --rules 可覆盖）
├── data/
│   ├── surnames.txt     # 常见姓氏表（内置，可被 rules.yaml 覆盖）
│   └── departments.txt  # 常见部门词表（内置，可被 rules.yaml 覆盖）
└── docs/
    └── rules_guide.md   # 规则编写指南（全字段说明 + 扩展清单）
tests/
├── fixtures/            # 12 类文档样例 + 4 种报销包 + 扩展 rules.yaml（真实样例 + 期望输出）
├── test_smoke.py  test_models.py  test_config.py  test_rules_yaml.py
├── test_extractors_base.py
├── test_rule_party_a.py  test_rule_person.py  test_rule_item.py
├── test_rule_department.py  test_rule_topic.py  test_rule_invoice_title.py
├── test_llm_extractor.py（mock）  test_material_detector.py
├── test_normalizers.py  test_doc_type.py  test_subtype.py  test_classifier.py
├── test_pipeline.py  test_metrics.py  test_cli.py
└── test_config_driven.py
```

> 说明：`rules.yaml` 随包内置作为默认规则；CLI 的 `--rules` 参数可指向任意规则文件（包内/外部均可）。`data/*.txt` 词表由抽取器加载，可被 rules.yaml 中同名字段覆盖。

### 4.3 关键接口契约

```python
@dataclass
class Section:
    index: int          # 分节/页序号（0 起）
    text: str

@dataclass
class RecognizedDoc:
    doc_id: str
    text: str                          # 全文（各分节拼接）
    sections: list[Section] | None = None   # 页/分节结构；None = 无分节信息，按全文处理
    structured: dict | None = None
    source: str = ""

# 抽取器统一契约（规则与 LLM 同构，可替换）
class Extractor(Protocol):
    name: str
    def extract(self, doc: RecognizedDoc, field: str, ctx: ExtractContext) -> list[Candidate]: ...

# 材料检测契约（①b；材料定义全部来自 rules.yaml，引擎不硬编码）
class MaterialDetector(Protocol):
    name: str
    def detect(self, doc: RecognizedDoc, material: "MaterialSpec", ctx: ExtractContext) -> list[MaterialHit]: ...

@dataclass
class Candidate:
    value: str            # 原始命中值
    field: str            # 目标维度名（party_a_name / person_name / item_name / department_name / meeting_name / invoice_title）
    confidence: float     # 0~1
    source: str           # "rule" | "llm"
    span: tuple[int, int] | None   # 证据在全文中的位置（LLM 送文 span 由 pipeline 映射回全文坐标）

@dataclass
class MaterialHit:
    material: str         # materials 定义中的材料名（如 "invoice"）
    display: str          # 显示名（如 "发票"）
    section: int | None   # 命中分节；None = 全文检测（无分节信息时的降级）
    confidence: float
    keyword: str          # 命中的关键词（证据）
    degraded: bool = False  # 全文降级检测标记

@dataclass
class Evidence:
    source: str           # "rule" | "llm" | "material" | "doc_type"
    value: str            # 命中值 / 关键词
    span: tuple[int, int] | None
    confidence: float

@dataclass
class Classification:
    doc_id: str
    doc_type: str | None = None     # 文档类型 key；无法判定时 None
    subtype: str | None = None      # 子类型 key（报销类型）；未启用或无命中为 None
    dimension: str | None = None    # 实际采用的主维度
    category_key: str | None = None # 主维度归一化键（扁平，用于分组/建目录）
    category_display: str | None = None  # 主维度展示名
    category_path: list[str] = field(default_factory=list)   # 层级归档路径
    materials: list[str] = field(default_factory=list)       # 命中的材料名（证据）
    confidence: float = 0.0
    evidence: list[Evidence] = field(default_factory=list)
    status: str = "unknown"         # "classified" | "review" | "unknown"
```

**候选合并规则（④⑤ 钉死）**

1. 每个 `Candidate.value` 先按维度 `normalize` 策略归一化；
2. 按 `(field, 归一化值)` 分组：组内 `confidence = max`，evidence 保留所有来源；
3. 每个 field 内取置信度最高的值作为该维度终值；
4. 维度"通过" = 终值 `confidence ≥` 该维度 `threshold`；
5. **主维度** = 通过的维度中 priority 最小者；其余通过的维度按 priority 依次进路径；
6. 完全无候选 → `status = "unknown"`；有候选但无维度通过 → `status = "review"`（不猜）。

**路径构造规则（⑥ 钉死，全设计唯一口径）**

```
category_path = [doc_type.display]
              + [subtype.display]（仅当配置了 subtypes 且命中）
              + [各通过维度值，按 priority 升序]
```

- `status = "classified"`：按上式完整生成；`status = "review"`：`[doc_type.display]`；`status = "unknown"`：`[]`。
- `category_key` = 主维度归一化值；`category_display` = 主维度原始值；`confidence` = 主维度终值置信度（review/unknown 时为最高候选置信度或 0）。
- 示例（同一口径）：合同 `["合同", "阿里巴巴（中国）有限公司"]`；差旅报销包 `["报销", "差旅费报销", "张三"]`；会议纪要 `["会议纪要", "Q4营销方案评审", "市场部"]`（次维度通过时也进路径）；`review` → `["报销"]`（仅 doc_type 段）；`unknown` → `[]`。
- **子类型层启用后的状态语义（钉死）**：doc_type 配置了 `subtypes` 时，①c 无候选（required 不全命中）或并列 → 最终 `status = "review"`（路径 `[doc_type.display]`，`subtype = None`），**即使维度候选存在也不自动归档**——报销材料不全/类型有歧义时必须人工判定（成功标准 #5）。若业务上单页报销单也需直接按人归档，在 `options` 增加轻量 option（如 `required: [approval]`）即可——**配置即解决，不改代码**。

**LLM 调用策略（③ 钉死）**

- **触发（钉死）**：**主维度**（生效维度中 priority 最小者）规则后未达阈值（含零候选），且主开关开启，才发起调用；待补字段 = 所有未达阈值且 `llm_fallback: true` 的维度。**主维度已达标 → 不调用 LLM**（次要维度缺失只影响路径段数，不值得一次调用；env `DOC_CLASSIFIER_LLM=off` 优先级最高，可强制关闭）。
- **每文档一次调用**：对所有待补维度一次性请求，模型返回严格 JSON `{"<field>": {"value","span","confidence"} | null, ...}`；`extract_fields(doc, fields, ctx)` 为批量入口（单维度 `extract` 委托给它）。
- **送文选择**：有 `sections` → 只送含规则命中的分节（拼接去重）；规则全未命中 → 送第一个分节；`sections is None` → 送全文（合规敏感场景应关闭主开关）。
- **重试与降级**：超时 / 5xx / JSON 解析失败 → 重试至 `llm.max_retries`；仍失败 → 降级为规则结果，记 warning 并在 summary 计 `llm_failed`。
- **缓存**：进程内 dict，key = `(model, sha256(送文), fields 元组)`，避免同批重复调用（不做 SQLite）。

### 4.4 rules.yaml 形态（v1.3 schema）

```yaml
version: "1.3"                   # 字符串（pydantic 按 str 校验，保持引号）

llm:                            # LLM 兕底总配置（默认关闭，可整体禁用）
  enabled: false                # 主开关；env DOC_CLASSIFIER_LLM=on/off 可覆盖
  base_url: ""                  # OpenAI 兼容网关（可指向内网模型）
  api_key_env: OPENAI_API_KEY   # 从该 env 读 key，不在文件里写 key
  model: ""
  timeout_sec: 20
  max_retries: 2

# 维度：一条维度 = 抽取器 + 归一化 + 标签集 + 是否允许 LLM 兕底 + 通过阈值
# labels 为字段标签集（配置驱动）：规则抽取器按集合匹配，如 "报销人：张三" 命中 person_name
dimensions:
  party_a_name:    { extractor: party_a,       normalize: org,    llm_fallback: false, threshold: 0.6,  labels: [甲方, 甲方名称] }
  person_name:     { extractor: person,        normalize: person, llm_fallback: true,  threshold: 0.6,  labels: [姓名, 报销人, 请假人, 申请人, 联系人, 作者] }
  item_name:       { extractor: item,          normalize: item,   llm_fallback: true,  threshold: 0.55, labels: [品名, 货物名称, 物料] }
  department_name: { extractor: department,    normalize: org,    llm_fallback: false, threshold: 0.6,  labels: [部门, 所在部门, 发文单位, 发文部门] }
  meeting_name:    { extractor: topic,         normalize: topic,  llm_fallback: false, threshold: 0.55, labels: [会议主题, 议题] }
  invoice_title:   { extractor: invoice_title, normalize: org,    llm_fallback: false, threshold: 0.6,  labels: [购方名称, 购买方名称] }

# 文档类型 → 用哪些维度（priority 越小越优先）
# 判定计分：score = 命中关键词的 distinct 数（同一关键词出现多次只计一次）；≥ min_score 判中
# 多个 doc_type 判中 → 分数高者胜；仍并列 → 整篇进 review（不猜，doc_type 取配置顺序首个供展示）
document_types:
  contract:
    display: 合同
    detect: { keywords: [甲方, 乙方, 签订, 合同], min_score: 1 }
    dimensions: [ { use: party_a_name, priority: 1 }, { use: person_name, priority: 2 } ]
  resume:
    display: 简历
    detect: { keywords: [教育经历, 工作经历, 求职, 简历], min_score: 1 }
    dimensions: [ { use: person_name, priority: 1 } ]
  purchase_order:
    display: 采购单
    detect: { keywords: [采购, 供应商, 收货, 单价], min_score: 1 }
    dimensions: [ { use: item_name, priority: 1 } ]

  # —— 日常办公文件（v1.1 新增）——
  meeting_minutes:
    display: 会议纪要
    detect: { keywords: [会议纪要, 参会人员, 议题, 决议], min_score: 2 }
    dimensions: [ { use: meeting_name, priority: 1 }, { use: department_name, priority: 2 } ]
  reimbursement:
    display: 报销
    detect: { keywords: [报销, 发票, 费用明细, 报销人], min_score: 2 }
    dimensions: [ { use: person_name, priority: 1 }, { use: department_name, priority: 2 } ]
    subtypes:                        # 子类型层（v1.2；v1.4 移入 doc_type 字段下；无此段 = 不启用，零开销）
      materials:                     # 材料定义（全配置化 v1.3）：材料名 → 显示名 + 关键词特征
        invoice:   { display: 发票,     keywords: [发票, 发票号码, 价税合计] }
        itinerary: { display: 行程单,   keywords: [行程单, 车票, 登机牌, 机票] }
        hotel:     { display: 住宿单,   keywords: [住宿, 酒店, 房费] }
        meal:      { display: 餐费单,   keywords: [餐费, 餐饮, 菜单] }
        taxi:      { display: 出租车票, keywords: [出租车, 滴滴, 网约车] }
        approval:  { display: 审批单,   keywords: [报销单, 审批, 报销人] }
        # 新增材料只需在此加一行，引擎按关键词检测，无需改代码
        # 高级材料可指定 detector: <注册名> 使用自定义检测器（可选，默认 keyword）
      options:
        travel_expense:              # 差旅费报销
          display: 差旅费报销
          required: [invoice, itinerary]   # 必需材料，缺一则不成为候选
          optional: [hotel, taxi]
          dimensions: [ { use: person_name, priority: 1 } ]   # 可覆盖默认维度
        hospitality:
          display: 业务招待费报销
          required: [invoice, meal, approval]
          optional: []
        office_supplies:
          display: 办公用品报销
          required: [invoice, approval]
          optional: []
      # 判定（①c）：required 全命中才有候选资格；计分 = required 命中×weight_required（默认 2）
      # + optional 命中×weight_optional（默认 1），权重可配；最高分胜出，并列/无候选 → review

  leave_request:
    display: 请假单
    detect: { keywords: [请假, 事假, 病假, 年假, 销假], min_score: 1 }
    dimensions: [ { use: person_name, priority: 1 } ]
  invoice:
    display: 发票
    detect: { keywords: [发票, 税号, 价税合计, 开票], min_score: 2 }
    dimensions: [ { use: invoice_title, priority: 1 } ]
  notice:
    display: 通知公告
    detect: { keywords: [通知, 公告, 各部门, 兹定于], min_score: 1 }
    dimensions: [ { use: department_name, priority: 1 } ]
  weekly_report:
    display: 周报/工作总结
    detect: { keywords: [本周, 下周计划, 工作总结, 周报], min_score: 2 }
    dimensions: [ { use: person_name, priority: 1 } ]
  policy:
    display: 规章制度
    detect: { keywords: [管理办法, 管理规定, 制度, 实施细则], min_score: 1 }
    dimensions: [ { use: department_name, priority: 1 } ]
  certificate:
    display: 证明材料
    detect: { keywords: [兹证明, 特此证明, 兹有], min_score: 1 }
    dimensions: [ { use: person_name, priority: 1 } ]
  personnel_record:
    display: 人事档案
    detect: { keywords: [入职, 离职, 劳动合同, 员工档案], min_score: 1 }
    dimensions: [ { use: person_name, priority: 1 } ]

unknown_policy: { status: review, dimension: none }   # 无法分类的去向
```

**配置校验规则（`load_rules` 强制，不满足则报清晰错误）**：`document_types.dimensions[].use` 必须存在于 `dimensions`；`options.required/optional` 引用的材料必须已在 `materials` 定义；`detector` 注册名必须已注册；`options` 至少有一个 `required` 材料；无 `subtypes` 段时完全向后兼容。

### 4.5 内置文档类型 × 维度映射（含日常办公文件）

| 文档类型 | 判定关键词（示例） | 主维度 | 次维度 | 分类效果示例（路径口径见 4.3） |
|---|---|---|---|---|
| 合同 | 甲方 / 乙方 / 签订 | 甲方名称 | 人名 | `合同/阿里巴巴（中国）有限公司/` |
| 简历 | 教育经历 / 工作经历 | 人名 | — | `简历/张三/` |
| 采购单 | 采购 / 供应商 / 单价 | 物品名称 | — | `采购单/笔记本电脑/` |
| 会议纪要 | 会议纪要 / 议题 / 决议 | 会议主题 | 部门 | `会议纪要/Q4营销方案评审/市场部/` |
| 报销单 | 报销 / 发票 / 报销人 | 人名（报销人） | 部门 | 材料组合可判 → `报销/差旅费报销/张三/`；判不出 → `review` 队列（见 4.3 状态语义） |
| 请假单 | 请假 / 病假 / 年假 | 人名（请假人） | — | `请假单/李四/` |
| 发票 | 发票 / 税号 / 价税合计 | 发票抬头（购方） | — | `发票/XX信息技术有限公司/` |
| 通知公告 | 通知 / 公告 / 兹定于 | 发文部门 | — | `通知公告/人力资源部/` |
| 周报/工作总结 | 本周 / 下周计划 / 周报 | 人名 | — | `周报/工作总结/王五/` |
| 规章制度 | 管理办法 / 规定 / 实施细则 | 发文部门 | — | `规章制度/行政部/` |
| 证明材料 | 兹证明 / 特此证明 | 人名 | — | `证明材料/赵文杰/`（3 字名；2 字名无标签邻接不达标，见置信度规则） |
| 人事档案 | 入职 / 离职 / 劳动合同 | 人名 | — | `人事档案/张三/` |

**新增的三个维度（v1.1）**：

- `department_name`（部门）：标签匹配（`labels`：部门/所在部门/发文单位/发文部门）+ 组织后缀模式（`XX部/中心/科/组/处/办公室/委员会`），归一化复用 `org`；常见部门词表 `data/departments.txt` 辅助校验。
- `meeting_name`（会议主题）：`labels`：会议主题/议题 + `关于(.+?)的会议纪要` 提取式模式，归一化 `topic`（去首尾修饰词、统一标点）。
- `invoice_title`（发票抬头）：默认取**购方名称**（`labels`：购方名称/购买方名称，避免裸 `名称:` 误匹配）；命中行 ±3 行内出现 18 位统一社会信用代码则置信度 +0.2（上限 1.0）；销方歧义在 rules_guide 中说明配置项。

**维度复用说明**：报销人 / 请假人 / 周报作者 / 证明对象均复用 `person_name` 维度——同一实体维度在不同文档类型中只是**字段标签不同**。抽取器按 `DimensionSpec.labels` 声明的标签集匹配（内置默认 `姓名｜报销人｜请假人｜申请人｜联系人｜作者`，**可在 rules.yaml 中覆盖**，无需改代码）。

**人名抽取置信度规则（防误报钉死）**：标签邻接命中 0.9；称谓邻接（先生/女士/同志/经理/老师）0.8；姓氏表 + 3 字名 0.6；姓氏表 + 2 字名且**无**标签/称谓邻接 → 0.4（低于阈值 0.6，不通过）。同值候选按 4.3 合并规则取 max。

**后续可扩展维度**（日期、项目编号、资产编号等）：新增一个 extractor + 一条 dimension 配置即可，引擎零改动，写入 `docs/rules_guide.md` 扩展清单。

### 4.6 层级分类：材料组合 → 报销类型 → 维度归类（v1.2）

**需求**：报销时需提交多种类型资料，不同报销类型所需的材料组合不同。因此报销场景需要**两层分类**：

```
第 1 层：子类型判定（①b 材料检测 + ①c 材料组合计分）
   报销包材料集 = {发票, 行程单, 住宿单, 餐费单, 审批单, …}（按页/分节检测）
        │  按各 option 的 required/optional 清单计分
        ▼
   报销类型 = 差旅费报销 / 业务招待费报销 / 办公用品报销 / …
        ▼
第 2 层：维度分类（沿用 ②–⑥，报销类型可覆盖默认维度）
   差旅费报销 → 按 报销人(person_name) 归档
   最终归档路径：报销/差旅费报销/张三/
```

**设计要点**：

- **材料全配置化（v1.3 核心收紧）**：**引擎不硬编码任何一种材料或报销类型**。材料在 `subtypes.materials` 中定义（材料名 + 显示名 + 关键词特征），报销类型在 `subtypes.options` 中定义（required/optional 清单 + 计分权重 + 维度覆盖）。引擎只提供一个通用 `KeywordMaterialDetector`（契约见 4.3 `MaterialDetector`），按配置的关键词对报销包每页/分节文本检测得到材料集合（支持一包多张发票、多页混排）。**新增一种材料 = 加一行配置；新增一种报销类型 = 加一个 option，均不改代码**。高级场景（如需版式/表格特征识别的材料）通过抽取器注册表挂自定义检测器类，配置里以 `detector: <注册名>` 引用（可选项，默认 `keyword`）。
- **子类型判定器（①c，`subtype.py`）**：`required` 材料全命中才有候选资格；计分 = required 命中×W_req + optional 命中×W_opt（**权重可配，默认 2/1**）；最高分胜出，**并列或无候选 → `review`**（不猜）。
- **维度覆盖**：每种 option 可在配置中覆盖默认维度（如差旅报销仅按报销人），未配置则继承 doc_type 默认维度。
- **通用化**：这是通用"子类型层"，不绑定报销——任何 doc_type 只要配置了 `subtypes` 段即可启用（如合同按合同类型分子层）。**无该配置的文档类型零开销，行为与 v1.1 完全一致**（回归测试保护）。
- **无分节降级**：`RecognizedDoc.sections is None`（OCR 未分节）时，材料检测对全文执行并标记 `degraded=True`（置信度降档 0.7→0.55），分类照常进行，evidence 中保留降级标记。
- **报销包 doc_type 误判防护（钉死）**：① 判定文本取**首分节**（`sections[0]`，无分节时用全文）。报销包首页通常是审批单/报销单（命中 `报销/报销人`），避免包内发票页的 `发票/价税合计/税号` 关键词让 `invoice` 文档类型反超。材料检测 ①b 仍用**全部分节**，两者输入不同是刻意的。
  - **无分节包的已知风险**：`sections is None` 时全文判定，报销/发票关键词可能并列 → `review`（安全侧）。识别流水线应尽量提供 `sections`（OCR 分页天然可得）；rules_guide 已注明。
- **状态语义**：①c 无候选或并列 → 最终 `status = "review"`（不猜）；唯一最优 → 命中并继续 ②–⑥。单页报销单（材料不全）同样进 review，逃生口见 4.3 状态语义。
- **输出**：`Classification` 的 `subtype` / `category_path` / `materials` 字段（定义见 4.3）；扁平 `category_key` 仍保留用于第 2 层分组。

### 4.7 技术选型

| 项 | 选型 | 说明 |
|---|---|---|
| 语言 | Python ≥ 3.11 | 与现有流水线一致 |
| 配置 | YAML + pydantic | 声明式 + 强校验，改规则不改代码 |
| LLM | OpenAI 兼容 `/v1/chat/completions` | 复用现有 NewAPI 网关（`llm:` 块配 base_url/model，key 从 env 读），**默认关闭** |
| 缓存 | 进程内 dict | LLM 结果按内容 hash 缓存（随 LLM 抽取器一起实现）；不做 SQLite（YAGNI） |
| 测试 | pytest | 规则路径全覆盖 + LLM 走 mock + fixtures 端到端 |

---

## 5. 关键风险与对策

| # | 风险 | 对策 |
|---|---|---|
| R1 | **实体归一化/消歧**：`阿里巴巴（中国）有限公司` vs `阿里巴巴(中国)有限公司`；同名不同人 | 归一化层统一全/半角、括号、去"有限公司/公司"后缀（key 去后缀、display 保留）；同名冲突保留多个候选并标 `review` |
| R2 | **LLM 输出不稳定** | 严格 JSON schema（pydantic）校验 + 重试（`llm.max_retries`）+ 失败降级为规则结果并计数 |
| R3 | **隐私合规**：文档内容送外部 LLM | `llm.enabled` 默认 **false**；开启时按 4.3 送文规则只送分节片段；`base_url` 可指向内网模型；env `DOC_CLASSIFIER_LLM=off` 强制关闭（优先级最高） |
| R4 | **多维度冲突**：一文档可分属多维度 | rules.yaml 显式 priority；按 4.3 合并规则取主维度，其余通过维度按 priority 进路径 |
| R5 | **规则词典冷启动维护成本** | `docs/rules_guide.md` + review 样本回流：CLI 输出 out.jsonl 中含全部 review/unknown 样本与证据，人工补判后可反向增补 rules.yaml 关键词 |
| R6 | **doc_type 判定错误/并列** | distinct 关键词计分 + min_score 阈值；多命中取高分；**并列 → review**（不猜）；低分可后续挂 LLM 判定钩子（第一版不做） |
| R7 | **报销包多材料混排**：一包多张发票、多页材料交叉 | 按页/分节检测材料集合（`sections`）；OCR 分节缺失（`sections is None`）时降级为全文检测并标记 `degraded` |
| R8 | **报销类型并列/材料不全** | required 门控 + 并列进 `review`；`materials` 字段保留证据，便于人工补判 |
| R9 | **材料关键词误检**（如"菜单"误命中其他语境） | 关键词最小长度约束 + 词边界/词频门槛；误检样本回流 `review` 队列反向优化关键词表（改 YAML 即可） |
| R10 | **2 字人名误报**（"李四"作普通词面） | 按 4.5 置信度规则：无标签/称谓邻接的 2 字名置信度 0.4，低于阈值不通过 |

---

## 6. 成功标准（验收）

1. 12 类文档**每类至少 1 个 e2e fixture**，对 fixture 批量输出分类结果，**核心样例全部命中期望路径与状态**。
2. **CLI 输出 summary 统计可度量**：规则层命中率 ≥ 70%，LLM 兕底调用率 ≤ 30%（在 fixture 批次上断言）。
3. 每条分类结果**带证据（span/keyword/source）可追溯**，unknown/review 进入复核而非静默丢弃。
4. 更换 `rules.yaml` 即可改变分类维度，**无需改代码**（有回归测试证明）。
5. **报销层级分类**：差旅/招待/办公用品三种材料组合样例全部判对子类型并生成正确 `category_path`；required 材料缺失时进 `review` 而非误判。
6. **材料/报销类型全配置化**：在 `rules.yaml` 中新增一种材料（如通讯费单）和一种报销类型（如通讯费报销），**不改任何代码**即可分类成功（回归测试证明）。
7. 核心路径单测覆盖，`pytest` 全绿。

---

## 7. 明确不做（YAGNI）

- ❌ 不做前端管理后台（第一版规则改 YAML 即可）。
- ❌ 不做数据库持久化（嵌入流水线，内存/JSON 进出）。
- ❌ 不做模型训练/微调（规则 + 通用 LLM 足够）。
- ❌ 不做多语言/跨语种分类（第一版只针对中文文档）。
- ❌ 不做 LLM 文档类型判定（① 仅保留预留钩子，第一版只有关键词计分）。
- ❌ 不做 SQLite 缓存（仅进程内 dict）。
- ❌ 日期 / 项目编号 / 资产编号等维度**不在第一版实现**（引擎已支持扩展，仅列入 `docs/rules_guide.md` 扩展清单，需要时补一个 extractor 即可）。

---

## 8. 修订记录

- **v1.4（本版，评审驱动修复）**：
  1. `RecognizedDoc` 增加 `sections` 分节模型（材料检测 ①b 的输入依据，修复"按页检测"无输入可依据的缺口）；
  2. 钉死 `category_path` 唯一构造规则并统一 4.3/4.5/4.6 全部示例（修复 4.5 与 4.3/R4 矛盾）；
  3. `subtypes` 从 `document_types` 保留键移入 doc_type 字段下（消除保留键冲突）；
  4. 字段标签集合配置化（`DimensionSpec.labels`）；
  5. 顶层 `llm:` 配置块，主开关默认关闭（修复 R3 与示例 yaml 全部 `llm_fallback: true` 的矛盾；示例中改为按需开启）；
  6. 钉死三组决策：doc_type 并列→review、规则/LLM 候选合并规则、LLM 每文档一次调用 + 送文/重试/缓存策略；
  7. 补齐 `MaterialDetector` / `MaterialHit` 契约、`subtype.py` / `material.py` / `data/` 入模块结构；
  8. 发票标签去掉裸 `名称:`（防误匹配）；新增 R10（2 字人名防误报置信度规则）；
  9. 成功标准 #1 明确 12 类 fixture 覆盖、#2 明确 summary 可度量；
  10. rules.yaml 示例 `version` 升 1.3（与 subtypes schema 对齐）；明确 `rules.yaml` 随包内置 + `--rules` 覆盖的位置口径；
  11. ① doc_type 判定文本改为**首分节**（无分节用全文），防报销包内发票页让 `invoice` 类型反超；①b 材料检测仍用全部分节；
  12. 钉死子类型层启用后的状态语义：①c 无候选/并列 → 最终 `review`（即使维度候选存在）；单页报销单示例与 4.3 路径口径统一，并给出 options 轻量配置逃生口。
- **v1.3**：材料 / 报销类型全配置化（新增材料或报销类型不改代码）。
- **v1.2**：报销层级分类（材料组合 → 报销类型 → 维度归类）。
- **v1.1**：9 类日常办公文档 + 3 个新维度（部门/会议主题/发票抬头）。
- **v1.0**：3 类业务文档 + 3 维度 + 6 段流水线 + 3 方案对比。

