# doc-classifier · 维度涌现式文档分类引擎

> 文档 → **先识别内容，再依据识别出的关键词所属维度（人名 / 物品 / 甲方 / 部门 / 议题 / 发票抬头）动态决定分类方式**。
> 规则优先 + LLM 兜底（默认关闭）+ **全配置驱动**（新维度/新文档类型/新材料 = 只改 YAML，不改代码）。

设计规格：[`design.md`](design.md)（v1.4）· 实现计划：[`plan.md`](plan.md) · 规则编写指南：[`doc_classifier/docs/rules_guide.md`](doc_classifier/docs/rules_guide.md)

## 流水线

```
RecognizedDoc(doc_id, text, sections?)
  → ① 文档类型（关键词计分 + 标题加权；首分节判定域；并列 → review）
  → ①b 材料检测（报销包多分节；无分节 → 全文降级）
  → ①c 子类型（required 门控 + 权重计分；无命中/并列 → review）
  → ②③ 维度抽取（规则 L1；主维度未达标才触发 LLM 兜底 L2）
  → ④ 候选合并（按 归一化值 分组，conf=max）
  → ⑤ 分类决策（阈值过滤；主维度=通过者中最小 priority；不猜）
  → ⑥ Classification + Summary（每条结果带证据 span/keyword/source）
```

状态语义（钉死）：**并列 / 低于阈值 → `review`（绝不猜）**；完全无候选 → `unknown`；子类型层启用而未命中 → `review`。

## 安装

```bash
python3.11+ -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt        # pydantic>=2 / PyYAML / pytest（openai 可选，仅启用 LLM 时需要）
pytest -q                              # 全量回归（87+ 用例，全 mock，无网络）
```

## CLI 用法

输入为 JSONL，每行一篇 `RecognizedDoc`；输出为 JSONL，每行一个 `Classification`；review/unknown 同样落盘（供人工复核回流）：

```bash
python -m doc_classifier.cli \
  --rules doc_classifier/rules.yaml \
  --input docs.jsonl \
  --output out.jsonl \
  --llm auto                 # auto=按配置 | on=强制开 | off=强制关
```

末尾向 stdout 打印批次指标：`共 N 篇 | classified x | review y | unknown z | 规则命中率 .. | LLM调用率 ..`

输入 schema 示例（`sections` 可省略；报销包等扫描件建议给出分节）：

```json
{"doc_id": "rb-001", "text": "", "sections": [
  {"index": 0, "text": "报销单 报销人：张三 审批：已通过"},
  {"index": 1, "text": "增值税普通发票 发票号码 价税合计 购方名称：… 税号：…"}
]}
```

输出 schema 示例：

```json
{"doc_id": "rb-001", "status": "classified", "doc_type": "reimbursement",
 "subtype": "travel_expense", "dimension": "person_name",
 "category_key": "张三", "category_path": ["报销", "差旅费报销", "张三"],
 "materials": ["approval", "invoice"],
 "evidence": [{"source": "rule", "value": "张三", "span": [5, 7], "confidence": 0.9}],
 "confidence": 0.9}
```

## Python 集成

```python
from doc_classifier.config import load_rules
from doc_classifier.pipeline import classify_doc, classify_docs
from doc_classifier.models import RecognizedDoc

rules = load_rules("doc_classifier/rules.yaml")
doc = RecognizedDoc(doc_id="c1", text="技术服务合同 甲方：阿里巴巴（中国）有限公司 …")
result = classify_doc(doc, rules)           # llm 默认 None = 纯规则
print(result.status, result.category_path)  # classified ['合同', '阿里巴巴（中国）有限公司']

results, summary = classify_docs([doc, ...], rules)   # 批量 + Summary 指标
```

## LLM 开关与合规

- 主开关：`rules.yaml` 的 `llm.enabled`（**默认 false**，全部测试在 LLM 关闭下运行）；
- env 优先级最高：`DOC_CLASSIFIER_LLM=off` 强制关闭；`on` 强制开启（`--llm on/off` 亦可覆盖配置）；
- 触发策略（钉死）：**主维度规则后未达阈值才调用**；每文档一次请求所有待补维度；重试 `llm.max_retries` 后降级为规则结果并计入 `summary.llm_failed`；内存缓存同文同字段不重复调用；
- 送文选择：有分节只送含规则命中的分节；无分节送全文（合规敏感场景请关闭主开关）；API key 从 `llm.api_key_env` 指定的环境变量读取，不落文件。

## 配置驱动扩展（零代码改动）

| 要扩展 | 只改哪里 |
|---|---|
| 新文档类型 | `document_types` 加一段（display/detect/dimensions） |
| 新报销类型/材料 | `reimbursement.subtypes.options / materials` 加一行 |
| 新字段标签 | 对应 `dimensions.<维度>.labels` 加词 |
| 换主维度 | `document_types.<类型>.dimensions` 改 `priority` |

完整字段语义与已知歧义：见 [rules_guide.md](doc_classifier/docs/rules_guide.md)。

## 测试

```bash
pytest -q                    # 单元 + e2e（12 类办公文档 + 报销包 5 组合 + 配置驱动回归）
pytest tests/test_metrics.py # 成功标准 #1/#2/#3 的批次指标断言
```
