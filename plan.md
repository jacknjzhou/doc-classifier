# 文档分类引擎实现计划（TDD）

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。
> 对应规格：`design.md`（v1.4，同目录）。计划的论证依据来自规格，执行者两份都读。

**目标：** 构建"维度涌现 + 全配置化"的 Python 文档分类引擎：已识别文档按 `rules.yaml` 得到 文档类型 → 材料/子类型 → 维度 → 规则抽取（LLM 兜底）→ 归一化 → 带证据的归档路径。

**架构：** 7 段流水线（① doc_type → ①b 材料检测 → ①c 子类型 → ② 维度 → ③ 抽取 → ④ 归一化 → ⑤ 决策 → ⑥ 输出+summary）；单一 `doc_classifier` 包，JSONL 进出，无数据库；维度/材料/报销类型/标签全部声明在 `rules.yaml`。

**技术栈：** Python ≥ 3.11 · pydantic v2 · PyYAML · openai（OpenAI 兼容网关）· pytest

## 执行约定

- 所有路径相对项目根 `/Users/jacky/works/doc-classifier/`（本计划为一次性全新执行，任务按依赖序编号，无增量回退）。
- venv 在 1 创建：`python3 -m venv .venv`；所有命令用 `.venv/bin/python`。
- 运行测试统一：`.venv/bin/python -m pytest tests/ -q`。
- 每个任务独立 commit：`feat(<模块>): <描述>`。

## 全局约束

- Python ≥ 3.11；只处理中文文档（第一版）。
- 无数据库持久化：内存 / JSONL 进出。
- LLM 主开关默认关闭（`llm.enabled: false`）；任何代码路径必须可离线跑通（测试全部 mock，不发真实请求）。
- 新增维度/材料/报销类型/字段标签/关键词 = 只改 `rules.yaml`，不改引擎代码（回归测试 22/23 保护）。
- 任何并列/低于阈值 → `review`，不猜；无候选 → `unknown`；每条结果必须带证据（span/keyword/source）。
- 子类型层启用（doc_type 配置了 `subtypes`）时：①c 无候选或并列 → 最终 `status="review"`，即使维度候选存在（design 4.3 状态语义）。
- ① doc_type 判定文本 = `sections[0].text`（有分节时）否则 `doc.text`；①b 材料检测用全部分节（design 4.6 钉死）。
- `category_path = [doc_type.display] + [subtype.display?] + [通过维度值按 priority]`；`review → [doc_type.display]`；`unknown → []`（design 4.3 唯一口径）。

## 审查重点

规格隐含的失败模式 → 期望行为 → 钉到任务（每条都有对应测试）：

| # | 失败模式 | 期望行为 | 钉到 |
|---|---|---|---|
| 1 | 同一机构全/半角括号、有无"有限公司"后缀 | 归一化为同一 `category_key` | 9 |
| 2 | 空文本 / 纯符号 OCR 垃圾文档 | status ∈ {unknown, review}，不抛异常 | 10, 14 |
| 3 | LLM 超时 / 返回非法 JSON | 重试耗尽 → 降级为规则结果，文档照常处理 | 8 |
| 4 | 报销包无分节（`sections=None`） | 全文检测 + `degraded=True`，subtype 判定与证据不丢 | 12, 21 |
| 5 | doc_type / 报销类型最高分并列 | `review`，不猜 | 10, 13 |
| 6 | 报销包内发票页污染 doc_type 判定 | 首分节判定 → 仍判为 `reimbursement` | 10 |

---

## 里程碑 M1 — 骨架与配置（1–4）

### 任务 1：项目骨架与依赖

**文件：**
- 创建：`pyproject.toml`、`requirements.txt`、`.gitignore`、`doc_classifier/__init__.py`、`doc_classifier/extractors/__init__.py`、`tests/__init__.py`、`tests/test_smoke.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_smoke.py
import doc_classifier

def test_version():
    assert doc_classifier.__version__ == "0.1.0"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python3 -m venv .venv && .venv/bin/python -m pytest tests/test_smoke.py -q`
预期：FAIL（ModuleNotFoundError: doc_classifier）

- [ ] **步骤 3：实现**

`pyproject.toml`（name=doc-classifier, version=0.1.0, requires-python>=3.11, dependencies=[pydantic>=2, PyYAML, openai, pytest]）、`requirements.txt`（同依赖列表）、`.gitignore`（`.venv/` `__pycache__/` `*.egg-info/` `.pytest_cache/`）、`doc_classifier/__init__.py`（`__version__ = "0.1.0"`）、空的 `extractors/__init__.py` 与 `tests/__init__.py`。
- 运行：`.venv/bin/pip install -r requirements.txt`

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_smoke.py -q`
预期：1 passed

- [ ] **步骤 5：Commit**

```bash
git init && git add -A && git commit -m "feat(skeleton): 项目骨架、依赖、smoke 测试"
```

### 任务 2：数据模型 models.py（最终形态，含 sections 与子类型字段）

**文件：**
- 创建：`doc_classifier/models.py`、`tests/test_models.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_models.py
from doc_classifier.models import (
    RecognizedDoc, Section, Candidate, Evidence, MaterialHit, Classification, SubtypeResult,
)

def test_recognized_doc_sections_optional():
    d = RecognizedDoc(doc_id="d1", text="abc")
    assert d.sections is None and d.structured is None
    d2 = RecognizedDoc(doc_id="d2", text="ab", sections=[Section(index=0, text="a")])
    assert d2.sections[0].text == "a"

def test_classification_defaults():
    c = Classification(doc_id="d1")
    assert c.status == "unknown" and c.subtype is None
    assert c.category_path == [] and c.materials == [] and c.confidence == 0.0

def test_material_hit_degraded_flag():
    h = MaterialHit(material="invoice", display="发票", section=None, confidence=0.55, keyword="发票")
    assert h.degraded is False

def test_subtype_result_defaults():
    s = SubtypeResult()
    assert s.option is None and s.display is None and s.tie is False and s.hits == {}
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_models.py -q`
预期：FAIL（ImportError: cannot import name ...）

- [ ] **步骤 3：实现 `doc_classifier/models.py`**

按 design 4.3 实现 7 个 `@dataclass`，字段/默认值逐字照抄设计：`Section(index, text)`、`RecognizedDoc(doc_id, text, sections=None, structured=None, source="")`、`Candidate(value, field, confidence, source, span=None)`、`MaterialHit(material, display, section, confidence, keyword, degraded=False)`、`Evidence(source, value, span, confidence)`、`SubtypeResult(option=None, display=None, tie=False, hits={})`（`hits: dict[str, MaterialHit]`）、`Classification(doc_id, doc_type=None, subtype=None, dimension=None, category_key=None, category_display=None, category_path=[], materials=[], confidence=0.0, evidence=[], status="unknown")`（可变默认用 `field(default_factory=...)`）。
**注意**：本任务一次到位（含 sections/subtype/category_path/materials/SubtypeResult），后续任务不得再改模型字段——避免回退式扩展。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_models.py -q`
预期：4 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/models.py tests/test_models.py && git commit -m "feat(models): 六个数据模型（最终形态）"
```

### 任务 3：配置 schema config.py + 抽取器基座（协议/注册表/conftest）

**文件：**
- 创建：`doc_classifier/config.py`、`doc_classifier/extractors/base.py`、`doc_classifier/extractors/registry.py`、`tests/conftest.py`、`tests/test_config.py`、`tests/test_extractors_base.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_config.py
import pytest
from pydantic import ValidationError
from doc_classifier.config import load_rules

GOOD = """
version: "1.3"
llm: { enabled: false }
dimensions:
  person_name: { extractor: person, normalize: person, labels: [姓名] }
document_types:
  resume:
    display: 简历
    detect: { keywords: [简历, 求职], min_score: 1 }
    dimensions: [{ use: person_name, priority: 1 }]
    subtypes:
      materials: { note: { display: 备注, keywords: [备注] } }
      options: { memo: { display: 备注报销, required: [note] } }
"""

def _write(tmp_path, text):
    p = tmp_path / "r.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)

def test_load_valid(tmp_path):
    rules = load_rules(_write(tmp_path, GOOD))
    assert rules.llm.enabled is False                      # 主开关默认关闭
    assert rules.dimensions["person_name"].labels == ["姓名"]
    assert rules.document_types["resume"].subtypes.options["memo"].required == ["note"]

def test_undefined_dimension_ref(tmp_path):               # use 引用未定义维度
    bad = GOOD.replace("use: person_name", "use: ghost")
    with pytest.raises(ValidationError, match="ghost"):
        load_rules(_write(tmp_path, bad))

def test_option_undefined_material(tmp_path):             # required 引用未定义材料
    bad = GOOD.replace("required: [note]", "required: [note, ghost]")
    with pytest.raises(ValidationError, match="ghost"):
        load_rules(_write(tmp_path, bad))

def test_unregistered_detector(tmp_path):                 # detector 未注册
    bad = GOOD.replace("keywords: [备注]", "keywords: [备注], detector: nope")
    with pytest.raises(ValidationError, match="nope"):
        load_rules(_write(tmp_path, bad))
```

```python
# tests/test_extractors_base.py
import pytest
from doc_classifier.extractors.base import Extractor, ExtractContext
from doc_classifier.extractors.registry import register_extractor, get_extractor

def test_registry_roundtrip():
    class Dummy(Extractor):
        name = "dummy"
        def extract(self, doc, field, ctx): return []
    register_extractor("dummy", Dummy())
    assert get_extractor("dummy").name == "dummy"

def test_unregistered_raises():
    with pytest.raises(KeyError):
        get_extractor("no_such_extractor")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_config.py tests/test_extractors_base.py -q`
预期：FAIL（ImportError）

- [ ] **步骤 3：实现**

`extractors/base.py`：`Extractor` / `MaterialDetector` Protocol（签名见 design 4.3）+ `@dataclass ExtractContext: rules: RulesConfig; degraded: bool = False`。
`extractors/registry.py`：两个注册表 dict，`register_extractor(name, ex)`、`get_extractor(name) -> Extractor`（未注册抛 KeyError）、`register_material_detector(name, det)`、`get_material_detector(name) -> MaterialDetector`（未注册抛 KeyError；`keyword` 由 12 导入时注册）。
`config.py`：pydantic 模型 `DimensionSpec(extractor, normalize, llm_fallback=False, threshold=0.6, labels=[])`、`DetectSpec(keywords, min_score=1)`、`DimensionRef(use, priority)`、`MaterialSpec(display, keywords, detector=None)`、`SubtypeOption(display, required, optional=[], weight_required=2.0, weight_optional=1.0, dimensions=[])`、`SubtypesSpec(materials: dict, options: dict)`、`DocTypeSpec(display, detect, dimensions, subtypes=None)`、`LLMConfig(enabled=False, base_url="", api_key_env="OPENAI_API_KEY", model="", timeout_sec=20.0, max_retries=2)`、`RulesConfig(version, llm=LLMConfig(), dimensions, document_types)`；`load_rules(path) -> RulesConfig`：读 YAML → `model_validate` → 交叉校验（use 已定义；required/optional ⊆ materials；detector 已注册；每个 option 至少 1 个 required；keywords 非空），错误信息含 offending 键名。
`tests/conftest.py`：`rules` fixture（`load_rules(包内 rules.yaml)`，供后续任务复用）+ `ctx` fixture（`ExtractContext(rules)`）。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_config.py tests/test_extractors_base.py -q`
预期：6 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/config.py doc_classifier/extractors/ tests/conftest.py tests/test_config.py tests/test_extractors_base.py && git commit -m "feat(config): 全量 schema（含 subtypes/llm/labels）+ 注册表 + conftest"
```

### 任务 4：默认规则 rules.yaml（12 类文档 + 6 维度 + 报销子类型）

**文件：**
- 创建：`doc_classifier/rules.yaml`、`tests/test_rules_yaml.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_rules_yaml.py
from pathlib import Path
from doc_classifier.config import load_rules

RULES = Path(__file__).resolve().parent.parent / "doc_classifier" / "rules.yaml"

def test_rules_yaml_loads():
    rules = load_rules(str(RULES))
    assert len(rules.document_types) == 12
    assert len(rules.dimensions) == 6
    assert "travel_expense" in rules.document_types["reimbursement"].subtypes.options
    assert rules.dimensions["person_name"].labels == ["姓名", "报销人", "请假人", "申请人", "联系人", "作者"]
    assert rules.llm.enabled is False
    assert rules.version == "1.3"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_rules_yaml.py -q`
预期：FAIL（FileNotFoundError）

- [ ] **步骤 3：实现**

`doc_classifier/rules.yaml` 逐字落地 design 4.4 的完整示例（`version: "1.3"` 保持引号、`llm:` 块默认 `enabled: false`、6 条维度含 `labels`、12 类文档、`reimbursement.subtypes` 6 材料 3 options）。`conftest.py` 的 `rules` fixture 依赖本文件。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/ -q`
预期：全部 passed（conftest 的 rules fixture 此时起可用）

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/rules.yaml tests/test_rules_yaml.py tests/conftest.py && git commit -m "feat(rules): 默认 rules.yaml（12 文档类型/6 维度/报销子类型）"
```

---

## 里程碑 M2 — 抽取器层（5–8）

### 任务 5：规则抽取器 — 甲方名称（party_a）

**文件：**
- 创建：`doc_classifier/extractors/rule.py`（PartyAExtractor）、`tests/test_rule_party_a.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_rule_party_a.py
from doc_classifier.models import RecognizedDoc
from doc_classifier.extractors.rule import PartyAExtractor
from doc_classifier.extractors.registry import register_extractor, get_extractor

import pytest
@pytest.fixture(autouse=True)
def _reg():
    register_extractor("party_a", PartyAExtractor())

def _ctx(rules):
    from doc_classifier.extractors.base import ExtractContext
    return ExtractContext(rules=rules)

def test_party_a_label(rules):
    doc = RecognizedDoc(doc_id="c1", text="甲方：阿里巴巴（中国）有限公司 乙方：某软件公司")
    cands = get_extractor("party_a").extract(doc, "party_a_name", _ctx(rules))
    hit = [c for c in cands if c.value == "阿里巴巴（中国）有限公司"]
    assert hit and hit[0].confidence >= 0.9
    assert doc.text[hit[0].span[0]:hit[0].span[1]] == hit[0].value   # span 可回溯

def test_party_a_name_variant(rules):
    doc = RecognizedDoc(doc_id="c2", text="甲方名称：杭州某某科技有限公司")
    cands = get_extractor("party_a").extract(doc, "party_a_name", _ctx(rules))
    assert any(c.value == "杭州某某科技有限公司" for c in cands)

def test_party_a_halfwidth_colon(rules):
    doc = RecognizedDoc(doc_id="c3", text="甲方: 北京字节网络技术有限公司")
    cands = get_extractor("party_a").extract(doc, "party_a_name", _ctx(rules))
    assert any(c.value == "北京字节网络技术有限公司" for c in cands)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_rule_party_a.py -q`
预期：FAIL（ImportError: cannot import name 'PartyAExtractor'）

- [ ] **步骤 3：实现 `rule.py` 的 `PartyAExtractor`**

`name = "party_a"`；正则 `(?:甲方(?:名称)?)[：:]\s*([^\s，。；;：:]{2,40})`，confidence 0.9，span = 捕获组在 `doc.text` 中的起止；标签集从 `ctx.dimension.labels` 读取（本维度为 `[甲方, 甲方名称]`，模式对标签循环）。在模块底部 `register_extractor("party_a", PartyAExtractor())`。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_rule_party_a.py -q`
预期：3 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/extractors/rule.py tests/test_rule_party_a.py && git commit -m "feat(rule): party_a 甲方名称抽取器"
```

### 任务 6：规则抽取器 — 人名（person，标签配置化 + 防误报置信度）

**文件：**
- 修改：`doc_classifier/extractors/rule.py`（PersonExtractor）、`doc_classifier/data/`（surnames.txt）
- 创建：`doc_classifier/data/surnames.txt`、`tests/test_rule_person.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_rule_person.py
from doc_classifier.models import RecognizedDoc
from doc_classifier.extractors.registry import get_extractor

import pytest
@pytest.fixture(autouse=True)
def _ctx(rules):
    from doc_classifier.extractors.base import ExtractContext
    return ExtractContext(rules=rules, degraded=False)

def _extract(doc, ctx):
    return get_extractor("person").extract(doc, "person_name", ctx)

def test_label_name(rules):
    doc = RecognizedDoc(doc_id="p1", text="姓名：张三 电话：13800000000")
    cands = _extract(doc, _ctx(rules))
    assert any(c.value == "张三" and c.confidence >= 0.9 for c in cands)

def test_label_reimburser_from_config(rules):     # labels 含 报销人（配置驱动）
    doc = RecognizedDoc(doc_id="p2", text="报销人：李四 部门：财务部")
    cands = _extract(doc, _ctx(rules))
    assert any(c.value == "李四" and c.confidence >= 0.9 for c in cands)

def test_honorific(rules):
    doc = RecognizedDoc(doc_id="p3", text="李四经理负责本次对接")
    cands = _extract(doc, _ctx(rules))
    assert any(c.value == "李四" and 0.7 <= c.confidence <= 0.9 for c in cands)

def test_bare_2char_below_threshold(rules):       # design R10：无邻接 2 字名不通过
    doc = RecognizedDoc(doc_id="p4", text="他跟李四喝了杯酒")
    cands = _extract(doc, _ctx(rules))
    assert all(c.confidence < 0.6 for c in cands)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_rule_person.py -q`
预期：FAIL（KeyError: 'person' 未注册）

- [ ] **步骤 3：实现 `PersonExtractor` + `data/surnames.txt`**

`name = "person"`，三策略（命中值按 (value) 去重，保留最高 conf）：
1. **标签邻接** 0.9：对 `ctx.dimension.labels`（person_name = 姓名/报销人/请假人/申请人/联系人）逐个 `label[：:]\s*([\u4e00-\u9fff]{2,10})`；
2. **称谓邻接** 0.8：`([\u4e00-\u9fff]{2,3})(?=\s?(?:先生|女士|同志|经理|老师|总监))`；
3. **姓氏表**：`data/surnames.txt`（常见 100 姓，每行一个，模块加载一次）——**只匹配独立中文 run（长度 2–3，前后为非中文或句界）**，首字在姓表 → 3 字名 0.6 / 2 字名 0.4（无策略 1/2 邻接时 0.4 < 阈值 0.6 不通过，design 4.5/R10）。**嵌入更长 run 的名字不产出**（避免把"李四喝"取成人名），交由 LLM 兕底。
span 取捕获组坐标。注册 `person`。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_rule_person.py -q`
预期：4 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/extractors/rule.py doc_classifier/data/ tests/test_rule_person.py && git commit -m "feat(rule): person 人名抽取器（标签配置化 + 2 字名防误报）"
```

### 任务 7：规则抽取器 — 物品（item）

**文件：**
- 修改：`doc_classifier/extractors/rule.py`（ItemExtractor）
- 创建：`tests/test_rule_item.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_rule_item.py
from doc_classifier.models import RecognizedDoc
from doc_classifier.extractors.registry import get_extractor
from doc_classifier.extractors.base import ExtractContext

def _extract(doc, rules):
    return get_extractor("item").extract(doc, "item_name", ExtractContext(rules=rules))

def test_item_label(rules):
    doc = RecognizedDoc(doc_id="i1", text="品名：笔记本电脑 数量：2 台 单价：5000")
    cands = _extract(doc, rules)
    assert any(c.value == "笔记本电脑" and c.confidence >= 0.9 for c in cands)

def test_item_unit_pattern(rules):
    doc = RecognizedDoc(doc_id="i2", text="本次采购 联想笔记本电脑 2台 及 打印纸 10 箱")
    cands = _extract(doc, rules)
    assert any(c.value == "联想笔记本电脑" for c in cands)
    assert any(c.value == "打印纸" for c in cands)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_rule_item.py -q`
预期：FAIL（KeyError: 'item'）

- [ ] **步骤 3：实现 `ItemExtractor`**

`name = "item"`：1) 标签邻接 0.9：对 `ctx.dimension.labels`（品名/货物名称/物料）`label[：:]\s*([^\s，。；;：:]{2,30})`；2) 单位模式 0.7：`([\u4e00-\u9fffA-Za-z0-9]{2,20}?)\s*(?=台|套|件|个|箱|盒)\s*\d+` 与 `\d+\s*(?=台|套|件|个|箱|盒)` 逆向取名。注册 `item`。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_rule_item.py -q`
预期：2 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/extractors/rule.py tests/test_rule_item.py && git commit -m "feat(rule): item 物品抽取器"
```

### 任务 8：LLM 兕底抽取器（每文档一次调用 + 重试降级 + 内存缓存）

**文件：**
- 创建：`doc_classifier/extractors/llm.py`、`tests/test_llm_extractor.py`

- [ ] **步骤 1：编写失败的测试（全部 mock，不发真实请求）**

```python
# tests/test_llm_extractor.py
import json
import pytest
from doc_classifier.models import RecognizedDoc
from doc_classifier.extractors.llm import LLMExtractor
from doc_classifier.extractors.base import ExtractContext

VALID = json.dumps({"person_name": {"value": "张三", "span": [3, 5], "confidence": 0.8}})

class FakeClient:
    def __init__(self, reply=VALID, fail=False):
        self.reply, self.fail, self.calls = reply, fail, 0
    def chat(self, messages):
        self.calls += 1
        if self.fail:
            raise TimeoutError("boom")
        class R: content = self.reply
        return R()

def _llm(rules, client, enabled):
    rules.llm.enabled = enabled
    return LLMExtractor(client=client)   # client 注入

def test_disabled_no_call(rules):
    c = FakeClient()
    llm = _llm(rules, c, enabled=False)
    doc = RecognizedDoc(doc_id="x", text="姓名：张三")
    assert llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules)) == {"person_name": []}
    assert c.calls == 0

def test_env_off_wins(rules, monkeypatch):
    monkeypatch.setenv("DOC_CLASSIFIER_LLM", "off")
    c = FakeClient()
    llm = _llm(rules, c, enabled=True)
    doc = RecognizedDoc(doc_id="x", text="姓名：张三")
    assert llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules))["person_name"] == []
    assert c.calls == 0

def test_valid_json(rules):
    c = FakeClient()
    llm = _llm(rules, c, enabled=True)
    doc = RecognizedDoc(doc_id="x", text="姓名：张三")
    out = llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules))
    assert out["person_name"][0].value == "张三" and out["person_name"][0].source == "llm"
    assert out["person_name"][0].confidence == 0.8

def test_bad_json_degrades(rules):
    c = FakeClient(reply="这不是JSON", fail=False)
    llm = _llm(rules, c, enabled=True)
    rules.llm.max_retries = 2
    doc = RecognizedDoc(doc_id="x", text="姓名：张三")
    out = llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules))
    assert out["person_name"] == [] and llm.failed >= 1   # 重试耗尽→降级，不抛异常

def test_cache_avoids_second_call(rules):
    c = FakeClient()
    llm = _llm(rules, c, enabled=True)
    doc = RecognizedDoc(doc_id="x", text="姓名：张三")
    llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules))
    llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules))
    assert c.calls == 1
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_llm_extractor.py -q`
预期：FAIL（ImportError: llm）

- [ ] **步骤 3：实现 `llm.py`**

`LLMExtractor(client=None)`：`client` 可注入（测试用）；默认按 `ctx.rules.llm`（base_url/api_key_env/model）惰性构造 OpenAI 兼容客户端。公开接口：
- `enabled(ctx) -> bool`：`ctx.rules.llm.enabled and os.environ.get("DOC_CLASSIFIER_LLM", "").lower() != "off"`；
- `extract_fields(doc, fields: list[str], ctx) -> dict[str, list[Candidate]]`：未启用 → 全空 dict；送文按 design 4.3（有 sections 送含规则命中的分节，否则首分节；`sections is None` 送全文）；prompt 要求严格 JSON `{"<field>": {"value","span","confidence"} | null}`；pydantic 校验响应 → `Candidate(source="llm")`，span 映射回全文坐标；失败（超时/5xx/解析失败）重试至 `llm.max_retries`，仍失败 → 该 field 返回 `[]` 且 `self.failed += 1`；
- 内存缓存：dict，key=`(model, sha256(送文), tuple(sorted(fields)))`；
- `extract(doc, field, ctx)` 委托 `extract_fields`；`self.calls`/`self.failed` 计数供 summary 使用。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_llm_extractor.py -q`
预期：5 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/extractors/llm.py tests/test_llm_extractor.py && git commit -m "feat(llm): 兕底抽取器（每文档一次调用/重试降级/内存缓存）"
```

---

## 里程碑 M3 — 决策层（9–11）

### 任务 9：归一化 normalizers.py（org / person / item）

**文件：**
- 创建：`doc_classifier/normalizers.py`、`tests/test_normalizers.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_normalizers.py
from doc_classifier.normalizers import normalize, normalize_org, normalize_person, normalize_item

def test_org_full_half_width():
    assert normalize_org("阿里巴巴（中国）有限公司") == normalize_org("阿里巴巴(中国)有限公司")

def test_org_suffix_variants():
    assert normalize_org("阿里巴巴科技有限公司") == normalize_org("阿里巴巴科技公司")

def test_org_inner_spaces():
    assert normalize_org("阿里巴巴 (中国) 有限公司") == normalize_org("阿里巴巴(中国)有限公司")

def test_person_title_strip():
    assert normalize_person("张三经理") == "张三"

def test_item_lower():
    assert normalize_item("LAPTOP") == "laptop"

def test_dispatch():
    assert normalize("阿里巴巴(中国)有限公司", "org") == normalize_org("阿里巴巴(中国)有限公司")
    assert normalize("张三经理", "person") == "张三"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_normalizers.py -q`
预期：FAIL（ImportError）

- [ ] **步骤 3：实现 `normalizers.py`**

- `normalize_org(v)`：全角→半角括号/冒号统一；去除所有空白；去后缀（`有限责任公司|股份有限公司|有限公司|公司`，从尾部循环剥离）；结果为空时回退 `v.strip().lower()`。
- `normalize_person(v)`：去称谓尾缀（先生|女士|同志|经理|老师|总监）与空白。
- `normalize_item(v)`：`lower()` + 去空白。
- `normalize_topic(v)`：本任务**不实现**（17 实现），但 `normalize(value, kind)` 分派 dict 预留 `"topic"` 键指向 `normalize_topic`（函数在 17 补入本文件）。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_normalizers.py -q`
预期：6 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/normalizers.py tests/test_normalizers.py && git commit -m "feat(normalize): org/person/item 归一化 + 分派"
```

### 任务 10：文档类型判定 doc_type.py（distinct 计分 + 首分节 + 并列 review）

**文件：**
- 创建：`doc_classifier/doc_type.py`、`tests/test_doc_type.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_doc_type.py
from doc_classifier.models import RecognizedDoc, Section
from doc_classifier.doc_type import detect_doc_type

def test_contract(rules):
    doc = RecognizedDoc(doc_id="t1", text="技术服务合同 甲方：某公司 乙方：另一公司 签订日期：2024-01")
    r = detect_doc_type(doc, rules)
    assert r.doc_type == "contract" and r.tied is False

def test_resume(rules):
    doc = RecognizedDoc(doc_id="t2", text="简历 教育经历：本科 工作经历：五年")
    assert detect_doc_type(doc, rules).doc_type == "resume"

def test_garbage_unknown(rules):
    doc = RecognizedDoc(doc_id="t3", text="###@@@!!!")
    r = detect_doc_type(doc, rules)
    assert r.doc_type is None

def test_distinct_counting(rules):
    # "合同"出现 3 次只计 1 个 distinct
    doc = RecognizedDoc(doc_id="t4", text="合同 合同 合同 甲方")
    r = detect_doc_type(doc, rules)
    assert r.scores["contract"] == 2 and r.doc_type == "contract"

def test_tie_goes_review(rules):
    doc = RecognizedDoc(doc_id="t5", text="甲方 合同 报销 发票")
    r = detect_doc_type(doc, rules)
    assert r.tied is True      # contract 2 vs reimbursement 2 → 并列

def test_first_section_wins(rules):   # 报销包：首页审批单，后页是发票（防 invoice 反超）
    doc = RecognizedDoc(doc_id="t6", text="报销单 报销人：张三 审批通过 发票 发票号码 价税合计 税号",
                        sections=[Section(index=0, text="报销单 报销人：张三 审批通过"),
                                  Section(index=1, text="增值税发票 发票号码：1 价税合计：100 税号：9133")])
    r = detect_doc_type(doc, rules)
    assert r.doc_type == "reimbursement"   # 首分节判定：reimbursement 2 > invoice 0
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_doc_type.py -q`
预期：FAIL（ImportError）

- [ ] **步骤 3：实现 `doc_type.py`**

`@dataclass DocTypeResult: doc_type: str | None; score: int; tied: bool; scores: dict[str, int]`；`detect_doc_type(doc, rules) -> DocTypeResult`：
- 判定文本 = `doc.sections[0].text if doc.sections else doc.text`（design 4.6 首分节规则）；
- 每个 doc_type：`score = distinct 命中关键词数`（同一关键词多次出现计 1）；`score ≥ min_score` 判中；
- 无判中 → `doc_type=None, score=0, tied=False`；唯一最高 → 胜出；**最高分并列 → `tied=True`，`doc_type` = 并列者中配置顺序首个**（供展示，pipeline 将整篇置 review）。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_doc_type.py -q`
预期：6 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/doc_type.py tests/test_doc_type.py && git commit -m "feat(doc_type): distinct 计分 + 首分节判定 + 并列标记"
```

### 任务 11：分类决策 classifier.py（候选合并 + 路径构造 + status）

**文件：**
- 创建：`doc_classifier/classifier.py`、`tests/test_classifier.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_classifier.py
from doc_classifier.models import RecognizedDoc, Candidate
from doc_classifier.classifier import classify
from doc_classifier.doc_type import DocTypeResult
from doc_classifier.models import SubtypeResult   # 2 定义；本任务用默认值/构造值

def _cand(value, field, conf, source="rule"):
    return Candidate(value=value, field=field, confidence=conf, source=source, span=None)

CT = DocTypeResult(doc_type="contract", score=2, tied=False, scores={"contract": 2})

def test_merge_same_normalized(rules):
    doc = RecognizedDoc(doc_id="c1", text="甲方：阿里巴巴（中国）有限公司")
    cands = [_cand("阿里巴巴（中国）有限公司", "party_a_name", 0.9),
             _cand("阿里巴巴(中国)有限公司", "party_a_name", 0.65, "llm")]   # 同 key，取 max
    c = classify(doc, CT, None, cands, rules)
    assert c.status == "classified" and c.dimension == "party_a_name"
    assert c.category_path == ["合同", "阿里巴巴（中国）有限公司"]
    assert c.confidence == 0.9

def test_secondary_dimension_in_path(rules):
    doc = RecognizedDoc(doc_id="c2", text="甲方：阿里巴巴（中国）有限公司 联系人：张三")
    cands = [_cand("阿里巴巴（中国）有限公司", "party_a_name", 0.9),
             _cand("张三", "person_name", 0.8)]
    c = classify(doc, CT, None, cands, rules)
    assert c.category_path == ["合同", "阿里巴巴（中国）有限公司", "张三"]

def test_below_threshold_review(rules):
    doc = RecognizedDoc(doc_id="c3", text="甲方：某公司")
    c = classify(doc, CT, None, [_cand("某公司", "party_a_name", 0.5)], rules)
    assert c.status == "review" and c.category_path == ["合同"] and c.subtype is None

def test_no_candidate_unknown(rules):
    doc = RecognizedDoc(doc_id="c4", text="x")
    c = classify(doc, CT, None, [], rules)
    assert c.status == "unknown" and c.category_path == []

def test_subtype_path(rules):
    doc = RecognizedDoc(doc_id="c5", text="报销")
    st = SubtypeResult(option="travel_expense", display="差旅费报销", tie=False, hits={})
    c = classify(doc, DocTypeResult("reimbursement", 2, False, {"reimbursement": 2}), st, [_cand("张三", "person_name", 0.9)], rules)
    assert c.category_path == ["报销", "差旅费报销", "张三"] and c.subtype == "travel_expense"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_classifier.py -q`
预期：FAIL（ImportError: classifier）

- [ ] **步骤 3：实现 `classifier.py`**

`classify(doc, doc_type_res, subtype_res, candidates, rules) -> Classification`，严格按 design 4.3 两组规则：
1. 合并：按 `(field, normalize(value, dim.normalize))` 分组 → 组内 `max(conf)`，evidence 全保留；每 field 取最高为终值；终值 `≥ dim.threshold` 记为"通过"；
2. 主维度 = 通过维度中 priority 最小；路径 = `[doc_type.display] + [subtype.display?（命中时）] + [通过维度**原始值**按 priority]`；
3. status：`doc_type_res.tied` 或（配置了 subtypes 且 subtype_res 为并列/无候选）→ `"review"`（路径 `[doc_type.display]`，subtype=None）；无候选 → `"unknown"`（路径 `[]`）；有候选无维度通过 → `"review"`；否则 `"classified"`；
4. `category_key` = 主维度归一化值、`category_display` = 主维度原始值、`confidence` = 主维度终值 conf（无则最高候选 conf 或 0）；`materials` = 命中的材料名列表。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_classifier.py -q`
预期：5 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/classifier.py tests/test_classifier.py && git commit -m "feat(classifier): 候选合并/路径构造/status 决策"
```

---

## 里程碑 M4 — 层级层与编排（12–16）

### 任务 12：通用材料检测器 material.py（全配置化，按分节/降级全文）

**文件：**
- 创建：`doc_classifier/extractors/material.py`、`tests/test_material_detector.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_material_detector.py
from doc_classifier.models import RecognizedDoc, Section
from doc_classifier.extractors.material import KeywordMaterialDetector
from doc_classifier.extractors.registry import get_material_detector
from doc_classifier.extractors.base import ExtractContext

def _package_doc(with_sections=True):
    secs = [Section(index=0, text="审批单 报销人：张三 审批通过"),
            Section(index=1, text="增值税普通发票 发票号码：1 价税合计：100"),
            Section(index=2, text="行程单 登机牌 北京-上海"),
            Section(index=3, text="住宿 酒店 房费 300")]
    return RecognizedDoc(doc_id="pkg", text=" ".join(s.text for s in secs),
                         sections=secs if with_sections else None)

def test_section_detection(rules):
    det = get_material_detector("keyword")
    hits = {}
    for name, spec in rules.document_types["reimbursement"].subtypes.materials.items():
        for h in det.detect(_package_doc(), spec, ExtractContext(rules=rules, degraded=False)):
            hits[h.material] = h
    assert set(hits) == {"invoice", "itinerary", "hotel", "approval"}
    assert all(not h.degraded for h in hits.values())

def test_fulltext_degraded(rules):          # sections=None → 全文检测 + degraded
    det = get_material_detector("keyword")
    hits = []
    for name, spec in rules.document_types["reimbursement"].subtypes.materials.items():
        hits += det.detect(_package_doc(with_sections=False), spec, ExtractContext(rules=rules, degraded=True))
    mats = {h.material for h in hits}
    assert {"invoice", "itinerary", "hotel", "approval"} <= mats
    assert all(h.degraded and h.section is None for h in hits)

def test_no_keyword_no_hit(rules):
    det = get_material_detector("keyword")
    doc = RecognizedDoc(doc_id="plain", text="今天天气不错")
    assert det.detect(doc, rules.document_types["reimbursement"].subtypes.materials["invoice"],
                      ExtractContext(rules=rules)) == []
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_material_detector.py -q`
预期：FAIL（KeyError: 'keyword' 未注册）

- [ ] **步骤 3：实现 `material.py`**

`KeywordMaterialDetector`（`name="keyword"`，模块导入时 `register_material_detector("keyword", ...)`）：
- 检测单元 = `doc.sections`（每分节一条）；`sections is None` 时单元 = 全文，命中记 `section=None, degraded=ctx.degraded`；
- 某材料在某单元：`material.keywords` 中每个 distinct 命中 +0.1（基础 0.7，degraded 基础 0.55，上限 0.9）；有命中则产出一条 `MaterialHit`（跨单元取最高 conf，`section` 取首个命中分节，`keyword` 取首个命中词）；
- 引擎不硬编码任何材料名——`materials` 完全来自 `ctx.rules`（由 pipeline 传入该 doc_type 的 `subtypes.materials`）；
- `detector: <注册名>` 非 `keyword` 时由 pipeline 改调 `get_material_detector(name)`（自定义检测器实现同一 Protocol）。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_material_detector.py -q`
预期：3 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/extractors/material.py tests/test_material_detector.py && git commit -m "feat(material): 通用关键词材料检测器（分节/降级/自定义可挂）"
```

### 任务 13：子类型判定器 subtype.py（required 门控 + 计分 + 并列 review）

**文件：**
- 创建：`doc_classifier/subtype.py`、`tests/test_subtype.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_subtype.py
from doc_classifier.subtype import resolve_subtype
from doc_classifier.models import MaterialHit

def _hit(name, display, conf=0.7):
    return MaterialHit(material=name, display=display, section=0, confidence=conf, keyword="x")

def _specs():   # 与 rules.yaml 报销一致的 option 结构
    from doc_classifier.config import SubtypesSpec, MaterialSpec, SubtypeOption
    return SubtypesSpec(
        materials={m: MaterialSpec(display=m, keywords=[m]) for m in ["invoice", "itinerary", "hotel", "taxi", "meal", "approval"]},
        options={
            "travel_expense": SubtypeOption(display="差旅费报销", required=["invoice", "itinerary"], optional=["hotel", "taxi"]),
            "hospitality": SubtypeOption(display="业务招待费报销", required=["invoice", "meal", "approval"]),
            "office_supplies": SubtypeOption(display="办公用品报销", required=["invoice", "approval"]),
        })

def _resolve(hit_names, display=None):
    hits = {n: _hit(n, display or n) for n in hit_names}
    return resolve_subtype(hits, _specs())

def test_travel(rules):
    r = _resolve(["invoice", "itinerary", "hotel"])
    assert r.option == "travel_expense" and r.tie is False   # 5 > office 4

def test_hospitality():
    r = _resolve(["invoice", "meal", "approval"])
    assert r.option == "hospitality"                          # 6 > office 4

def test_incomplete_none():
    r = _resolve(["invoice"])
    assert r.option is None and r.tie is False   # required 不全 → 无候选

def test_tie():
    from doc_classifier.config import SubtypesSpec, MaterialSpec, SubtypeOption
    spec = SubtypesSpec(
        materials={"a": MaterialSpec(display="A", keywords=["a"]), "b": MaterialSpec(display="B", keywords=["b"])},
        options={"o1": SubtypeOption(display="O1", required=["a"]), "o2": SubtypeOption(display="O2", required=["a"])})
    r = resolve_subtype({"a": _hit("a", "A")}, spec)
    assert r.option is None and r.tie is True     # 并列 → 不猜

def test_weights_configurable():
    from doc_classifier.config import SubtypesSpec, MaterialSpec, SubtypeOption
    spec = SubtypesSpec(
        materials={"a": MaterialSpec(display="A", keywords=["a"]), "b": MaterialSpec(display="B", keywords=["b"])},
        options={"o1": SubtypeOption(display="O1", required=["a"], optional=["b"], weight_optional=5.0)})
    r = resolve_subtype({"a": _hit("a", "A"), "b": _hit("b", "B")}, spec)
    assert r.option == "o1"    # 2 + 5×1 = 7（optional 权重生效）
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_subtype.py -q`
预期：FAIL（ImportError）

- [ ] **步骤 3：实现 `subtype.py`**

`resolve_subtype(hits: dict[str, MaterialHit], subtypes: SubtypesSpec) -> SubtypeResult`（`SubtypeResult` 来自 models）：
- 候选资格：`required ⊆ hits.keys()`；计分 = `|required∩hits|×weight_required + |optional∩hits|×weight_optional`（权重取 option 配置，默认 2/1）；
- 无候选 → `SubtypeResult(option=None, tie=False, hits=hits)`（pipeline 将最终 status 置 review，design 4.3 状态语义）；
- 唯一最高分 → 命中（`display` 取 option.display）；**最高分并列 → `tie=True, option=None`**。

- [ ] **步骤 4：运行测试通过**

运行：`.venv/bin/python -m pytest tests/test_subtype.py -q`
预期：5 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/subtype.py tests/test_subtype.py && git commit -m "feat(subtype): 材料组合 → 子类型判定（门控/权重/并列 review）"
```

### 任务 14：流水线编排 pipeline.py（①→⑥ + summary 统计）

**文件：**
- 创建：`doc_classifier/pipeline.py`、`tests/test_pipeline.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_pipeline.py
from doc_classifier.models import RecognizedDoc, Section
from doc_classifier.pipeline import classify_doc, classify_docs
from doc_classifier.extractors.llm import LLMExtractor

CONTRACT = RecognizedDoc(doc_id="c1",
    text="技术服务合同 甲方：阿里巴巴（中国）有限公司 乙方：某软件公司 签订日期：2024-01-01")

PKG = RecognizedDoc(doc_id="pkg", text="", sections=[
    Section(0, "报销单 报销人：张三 部门：财务部 审批通过"),
    Section(1, "增值税普通发票 发票号码：1 价税合计：100 购方名称：阿里巴巴（中国）有限公司 税号：91330106MA2XXXXXXX"),
    Section(2, "行程单 登机牌 北京-上海"),
    Section(3, "住宿 酒店 房费 300")])

def test_contract_end_to_end(rules):
    c = classify_doc(CONTRACT, rules, llm=None)
    assert c.status == "classified" and c.doc_type == "contract"
    assert c.category_path == ["合同", "阿里巴巴（中国）有限公司"]
    assert c.subtype is None

def test_reimburse_package_travel(rules):
    c = classify_doc(PKG, rules, llm=None)
    assert c.doc_type == "reimbursement" and c.subtype == "travel_expense"
    assert c.category_path == ["报销", "差旅费报销", "张三"]
    assert set(c.materials) == {"approval", "invoice", "itinerary", "hotel"}

def test_garbage_no_crash(rules):          # 审查重点 #2
    c = classify_doc(RecognizedDoc(doc_id="g", text="###@@@"), rules, llm=None)
    assert c.status in ("unknown", "review") and c.category_path in ([], )

def test_llm_not_called_when_rule_hits(rules):
    class CountingLLM(LLMExtractor):
        def __init__(self): super().__init__(client=None)
    llm = CountingLLM(); rules.llm.enabled = True
    c = classify_doc(CONTRACT, rules, llm=llm)
    assert llm.calls == 0                   # 主维度 party_a 已达标 → 不调用 LLM（次要维度缺失不触发）

def test_llm_fills_below_threshold(rules):
    doc = RecognizedDoc(doc_id="r1",
        text="个人简历 他跟李四聊了项目 教育经历" ,   # 2 字名无邻接 → 0.4 不达标
        sections=None)
    llm = LLMExtractor(client=FakeClient(reply=json.dumps(
        {"person_name": {"value": "李四", "span": [7, 9], "confidence": 0.8}})))
    rules.llm.enabled = True
    c = classify_doc(doc, rules, llm=llm)
    assert llm.calls == 1 and c.category_path == ["简历", "李四"]
```
（文件顶部补 `import json` 与从 `tests/test_llm_extractor.py` 复制的 `FakeClient`——或将其抽到 `tests/fakes.py` 共用。）

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_pipeline.py -q`
预期：FAIL（ImportError: pipeline）

- [ ] **步骤 3：实现 `pipeline.py`**

`classify_doc(doc, rules, llm=None) -> Classification` 编排（严格按 design 4.1）：
1. ① `detect_doc_type`（首分节文本）→ `tied` 或无命中：`tied` → review（路径 `[doc_type.display]`）；无命中 → `unknown`，直接返回；
2. ①b：若该 doc_type 配置 `subtypes`：对 `subtypes.materials` 逐个 `detector.detect`（默认 `keyword`；`detector:` 配置用 `get_material_detector`）；`ctx.degraded = doc.sections is None`；聚合 `hits: dict[material, MaterialHit]`（每材料取最高 conf）；
3. ①c：`resolve_subtype(hits, subtypes)` → `SubtypeResult`；
4. ②：维度 = subtype 命中且配置了 `dimensions` 覆盖时用覆盖，否则 doc_type 的 `dimensions`（priority 升序）；
5. ③：规则抽取器逐维度 `extract`（`get_extractor(dim.extractor)`）；LLM 触发（design 4.3 钉死）：**主维度（priority 最小）规则后未达阈值（含零候选）且 `llm.enabled` → 一次 `llm.extract_fields` 请求所有未达标且 `llm_fallback=true` 的维度**；主维度已达标 → 不调用；`llm is None` 或未启用 → 跳过；
6. ④⑤：`classify(...)` 产出 `Classification`；⑥：materials/evidence 填入。

`classify_docs(docs, rules, llm=None) -> tuple[list[Classification], Summary]`：`@dataclass Summary: total, classified, review, unknown, llm_docs, llm_calls, llm_failed, rule_hit_rate, llm_rate`（`llm_rate = llm_docs/total`，`rule_hit_rate = 1 - llm_rate`；`llm_docs` = 实际触发 ≥1 次 LLM 调用的文档数）。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_pipeline.py -q`
预期：5 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/pipeline.py tests/test_pipeline.py && git commit -m "feat(pipeline): ①→⑥ 编排 + summary 统计"
```

### 任务 15：CLI 入口 cli.py（JSONL 进出 + summary 输出 + review 回流）

**文件：**
- 创建：`doc_classifier/cli.py`、`tests/test_cli.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_cli.py
import json
from doc_classifier.cli import main

def test_cli_roundtrip(tmp_path, rules):
    inp, out = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    docs = [{"doc_id": "c1", "text": "技术服务合同 甲方：阿里巴巴（中国）有限公司"},
            {"doc_id": "g1", "text": "###@@@"}]
    inp.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in docs), encoding="utf-8")
    main(["--rules", str(RULES_PATH), "--input", str(inp), "--output", str(out)])
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["status"] == "classified" and first["category_path"][0] == "合同"
    assert json.loads(lines[1])["status"] in ("unknown", "review")   # review 样本落盘（R5 回流）
```
（`capsys` 断言 stdout 含 `规则命中率` 与 `LLM调用率` 两行 summary。）

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_cli.py -q`
预期：FAIL（ImportError）

- [ ] **步骤 3：实现 `cli.py`**

`main(argv=None) -> int`：argparse `--rules`（默认包内 `doc_classifier/rules.yaml`）、`--input`（JSONL，每行 `RecognizedDoc`）、`--output`（JSONL，每行 `Classification` 序列化，含 status/category_path/materials/evidence）、`--llm on|off|auto`（默认 auto=按配置；on/off 覆盖 `llm.enabled`）。逐行 `classify_doc`，末尾向 stdout 打印 summary（`共 N 篇 | classified x | review y | unknown z | 规则命中率 {..:.0%} | LLM调用率 {..:.0%}`）。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_cli.py -q`
预期：1 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/cli.py tests/test_cli.py && git commit -m "feat(cli): JSONL 批处理入口 + summary/review 回流输出"
```

### 任务 16：业务文档 fixtures 端到端（合同/简历/采购单）

**文件：**
- 创建：`tests/fixtures/contract.json`、`tests/fixtures/resume.json`、`tests/fixtures/purchase_order.json`；扩展 `tests/test_pipeline.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_pipeline.py（追加）
import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"
BUSINESS = {
    "contract":       (["合同", "阿里巴巴（中国）有限公司"], "classified"),
    "resume":         (["简历", "张三"], "classified"),
    "purchase_order": (["采购单", "笔记本电脑"], "classified"),
}

@pytest.mark.parametrize("name,path,status", BUSINESS.items())
def test_business_case(name, path, status, rules):
    doc = _load(str(FIX / f"{name}.json"))
    c = classify_doc(doc, rules, llm=None)
    assert c.category_path == path and c.status == status
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_pipeline.py -q`
预期：3 failed（fixture 文件不存在）

- [ ] **步骤 3：实现 fixtures（纯数据）**

`_load(path)` 反序列化为 `RecognizedDoc`（json → dataclass，`sections` 列表或缺省）。三份样例贴近真实识别输出：
- `contract.json`：技术服务合同正文（甲方：阿里巴巴（中国）有限公司 / 乙方 / 签订条款）；
- `resume.json`：姓名：张三 + 教育经历 + 工作经历；
- `purchase_order.json`：采购单（品名：笔记本电脑 数量：2台 供应商…）。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_pipeline.py -q`
预期：全部 passed

- [ ] **步骤 5：Commit**

```bash
git add tests/fixtures/ tests/test_pipeline.py && git commit -m "feat(fixtures): 合同/简历/采购单 e2e 用例"
```

---

## 里程碑 M5 — 日常办公文件（17–21）

### 任务 17：规则抽取器 — 部门（department）+ 部门词表

**文件：**
- 修改：`doc_classifier/extractors/rule.py`（DepartmentExtractor）
- 创建：`doc_classifier/data/departments.txt`、`tests/test_rule_department.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_rule_department.py
from doc_classifier.models import RecognizedDoc
from doc_classifier.extractors.registry import get_extractor
from doc_classifier.extractors.base import ExtractContext

def _extract(doc, rules):
    return get_extractor("department").extract(doc, "department_name", ExtractContext(rules=rules))

def test_label(rules):
    doc = RecognizedDoc(doc_id="n1", text="发文单位：人力资源部 兹定于周五开会")
    assert any(c.value == "人力资源部" and c.confidence >= 0.9 for c in _extract(doc, rules))

def test_suffix_pattern(rules):
    doc = RecognizedDoc(doc_id="n2", text="请财务部于本周五前提交报表")
    assert any(c.value == "财务部" for c in _extract(doc, rules))

def test_center_variant(rules):
    doc = RecognizedDoc(doc_id="n3", text="研发中心全体同事请注意")
    assert any(c.value == "研发中心" for c in _extract(doc, rules))
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_rule_department.py -q`
预期：FAIL（KeyError: 'department'）

- [ ] **步骤 3：实现 `DepartmentExtractor` + `data/departments.txt`**

`name = "department"`：1) 标签邻接 0.9（labels：部门/所在部门/发文单位/发文部门）`label[：:]\s*([\u4e00-\u9fff]{2,12})`；2) 组织后缀模式 0.7：`([\u4e00-\u9fff]{2,8}?(?:部|中心|科|组|处|办公室|委员会))`，且命中串需含 `data/departments.txt` 词表项或整体以后缀结尾（防"部分/部门感"类误报）。注册 `department`。
`data/departments.txt`：约 20 个常见部门（人力资源部/财务部/行政部/技术部/研发部/市场部/销售部/运营部/法务部/客服部/采购部/质管部/信息中心/审计部/培训部/战略发展部/数据部/安全部/公关部/总经办），每行一个。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_rule_department.py -q`
预期：3 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/extractors/rule.py doc_classifier/data/departments.txt tests/test_rule_department.py && git commit -m "feat(rule): department 部门抽取器 + 部门词表"
```

### 任务 18：规则抽取器 — 会议主题（topic）+ normalize_topic 完善

**文件：**
- 修改：`doc_classifier/extractors/rule.py`（TopicExtractor）、`doc_classifier/normalizers.py`（normalize_topic）
- 创建：`tests/test_rule_topic.py`；扩展 `tests/test_normalizers.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_rule_topic.py
from doc_classifier.models import RecognizedDoc
from doc_classifier.extractors.registry import get_extractor
from doc_classifier.extractors.base import ExtractContext

def _extract(doc, rules):
    return get_extractor("topic").extract(doc, "meeting_name", ExtractContext(rules=rules))

def test_topic_label(rules):
    doc = RecognizedDoc(doc_id="m1", text="会议主题：Q4 营销方案评审会 参会人员：…")
    assert any(c.value == "Q4 营销方案评审会" for c in _extract(doc, rules))

def test_topic_about_pattern(rules):
    doc = RecognizedDoc(doc_id="m2", text="关于年度审计的会议纪要")
    assert any(c.value == "年度审计" for c in _extract(doc, rules))

# tests/test_normalizers.py（追加）
def test_normalize_topic_strip():
    from doc_classifier.normalizers import normalize_topic
    assert normalize_topic("关于Q4营销方案评审的会议纪要") == normalize_topic("Q4营销方案评审")

def test_dispatch_topic():
    from doc_classifier.normalizers import normalize, normalize_topic
    assert normalize("关于X的会议纪要", "topic") == normalize_topic("关于X的会议纪要")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_rule_topic.py tests/test_normalizers.py -q`
预期：FAIL（KeyError: 'topic' / ImportError: normalize_topic）

- [ ] **步骤 3：实现**

`TopicExtractor`（`name="topic"`）：1) 标签 0.9（labels：会议主题/议题）`label[：:]\s*([^\s。；;]{2,30})`；2) 提取式 0.7：`关于(.+?)的会议纪要`；3) 回退 0.5：`doc.sections[0].text` 或 `doc.text` 的首行（去空白后长度 ≥ 2 且 ≤ 30 才取）。注册 `topic`。
`normalize_topic(v)`（补入 normalizers.py，9 预留的分派键生效）：去首部 `关于`、尾部 `的会议纪要|的讨论|的通知|会议纪要|会议`；全角→半角标点；去首尾空白；结果为空回退 `v.strip()`。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_rule_topic.py tests/test_normalizers.py -q`
预期：全部 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/extractors/rule.py doc_classifier/normalizers.py tests/test_rule_topic.py tests/test_normalizers.py && git commit -m "feat(rule): topic 会议主题抽取器 + normalize_topic"
```

### 任务 19：规则抽取器 — 发票抬头（invoice_title，购方 + 税号邻位校验）

**文件：**
- 修改：`doc_classifier/extractors/rule.py`（InvoiceTitleExtractor）
- 创建：`tests/test_rule_invoice_title.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_rule_invoice_title.py
from doc_classifier.models import RecognizedDoc
from doc_classifier.extractors.registry import get_extractor
from doc_classifier.extractors.base import ExtractContext

def _extract(doc, rules):
    return get_extractor("invoice_title").extract(doc, "invoice_title", ExtractContext(rules=rules))

def test_buyer_with_taxid_boost(rules):
    doc = RecognizedDoc(doc_id="v1", text="购方名称：XX信息技术有限公司 税号：91330106MA2B9C3D4E")
    cands = _extract(doc, rules)
    hit = [c for c in cands if c.value == "XX信息技术有限公司"]
    assert hit and hit[0].confidence >= 0.9 + 0.2 - 1e-9   # 税号邻位 +0.2，上限 1.0

def test_buyer_without_taxid(rules):
    doc = RecognizedDoc(doc_id="v2", text="购方名称：YY科技有限公司")
    cands = _extract(doc, rules)
    hit = [c for c in cands if c.value == "YY科技有限公司"]
    assert hit and 0.85 <= hit[0].confidence <= 0.95
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_rule_invoice_title.py -q`
预期：FAIL（KeyError: 'invoice_title'）

- [ ] **步骤 3：实现 `InvoiceTitleExtractor`**

`name = "invoice_title"`：对 `ctx.dimension.labels`（购方名称/购买方名称）`label[：:]\s*([^\s。；;]{2,40})` 基础 0.9；命中行 ±3 行内出现 18 位统一社会信用代码（`[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}`）→ +0.2（上限 1.0）。**不匹配裸 `名称:`**（design 4.5 防误匹配；取销方见 rules_guide 配置项）。注册 `invoice_title`。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_rule_invoice_title.py -q`
预期：2 passed

- [ ] **步骤 5：Commit**

```bash
git add doc_classifier/extractors/rule.py tests/test_rule_invoice_title.py && git commit -m "feat(rule): invoice_title 发票抬头抽取器（购方 + 税号邻位校验）"
```

### 任务 20：日常办公文件 fixtures 端到端（9 类全覆盖）

**文件：**
- 创建：`tests/fixtures/{meeting_minutes,reimbursement,leave_request,invoice,notice,weekly_report,policy,certificate,personnel_record}.json`；扩展 `tests/test_pipeline.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_pipeline.py（追加）
OFFICE = {
    "meeting_minutes":   (["会议纪要", "Q4营销方案评审", "市场部"], "classified"),
    "reimbursement":     (["报销"], "review"),     # 单页表单材料不全 → 子类型判不出 → review（design 4.3 状态语义）
    "leave_request":     (["请假单", "李四"], "classified"),
    "invoice":           (["发票", "XX信息技术有限公司"], "classified"),
    "notice":            (["通知公告", "人力资源部"], "classified"),
    "weekly_report":     (["周报/工作总结", "王五"], "classified"),
    "policy":            (["规章制度", "行政部"], "classified"),
    "certificate":       (["证明材料", "赵文杰"], "classified"),
    "personnel_record":  (["人事档案", "张三"], "classified"),
}

@pytest.mark.parametrize("name,path,status", OFFICE.items())
def test_office_case(name, path, status, rules):
    doc = _load(str(FIX / f"{name}.json"))
    c = classify_doc(doc, rules, llm=None)
    assert c.category_path == path and c.status == status, f"{name}: {c}"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_pipeline.py -q`
预期：9 failed（fixture 不存在）

- [ ] **步骤 3：实现 9 份 fixtures（纯数据，要点钉死）**

- `meeting_minutes`：标题含 `会议纪要`、正文含 `会议主题：Q4 营销方案评审` + `参会人员` + `议题` + `部门：市场部`（distinct 命中 ≥ min_score 2）；
- `reimbursement`：单页表单，文本含 `报销单/报销人：张三/部门：财务部/审批：已批准`，**不得出现 发票/发票号码/价税合计**（否则 ①b 命中 invoice 材料改变子类型判定）→ 材料 {approval} → 无 option 候选 → review；
- `leave_request`：`请假人：李四 请假 病假 3天`；
- `invoice`：`发票 发票号码 价税合计 购方名称：XX信息技术有限公司 税号：9133…`（≥2 doc_type 关键词）；
- `notice`：`通知 各部门 发文部门：人力资源部 兹定于`；
- `weekly_report`：`本周 工作总结 作者：王五`；
- `policy`：`管理办法 制度 发文部门：行政部`；
- `certificate`：`兹证明 赵文杰 系我单位员工`（**3 字名**：独立 run + 姓氏表 0.6 达标；2 字名无标签邻接会因 R10 不通过）；
- `personnel_record`：`员工档案 入职 姓名：张三 劳动合同`。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_pipeline.py -q`
预期：全部 passed（12 类文档 fixtures 至此齐备）

- [ ] **步骤 5：Commit**

```bash
git add tests/fixtures/ tests/test_pipeline.py && git commit -m "feat(fixtures): 9 类日常办公文档 e2e（12 类全覆盖）"
```

### 任务 21：批次指标回归（成功标准 #1/#2 可度量）

**文件：**
- 创建：`tests/test_metrics.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_metrics.py
from doc_classifier.pipeline import classify_docs

ALL = ["contract", "resume", "purchase_order", "meeting_minutes", "reimbursement",
       "leave_request", "invoice", "notice", "weekly_report", "policy", "certificate",
       "personnel_record"]

def test_batch_metrics(rules):
    docs = [_load(str(FIX / f"{n}.json")) for n in ALL]
    results, summary = classify_docs(docs, rules, llm=None)
    assert summary.total == 12
    assert summary.classified == 11 and summary.review == 1     # reimbursement 单页 → review
    assert summary.llm_docs == 0 and summary.rule_hit_rate == 1.0   # 全部规则命中（≥ 0.7 标准）
    assert summary.llm_rate == 0.0                              # ≤ 0.3 标准
    assert all(r.evidence for r in results if r.status == "classified")   # 证据可追溯
```
（`_load`/`FIX` 从 `tests/test_pipeline.py` 抽到 `tests/util.py` 共用，避免重复。）

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_metrics.py -q`
预期：FAIL（断言失败：classified 计数或 evidence 为空）

- [ ] **步骤 3：实现/修正**

本任务不新增引擎代码——若断言失败，回到对应任务定位（多为 fixture 关键词与 doc_type detect 的 distinct 计分不匹配）；同时把 `tests/test_pipeline.py` 的 `_load`/`FIX` 移入 `tests/util.py`（`Summary` 的 `rule_hit_rate`/`llm_rate` 属性若缺失则在 `pipeline.py` 补齐）。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/ -q`
预期：全量 passed（成功标准 #1/#2/#3 在 12 类集合上成立）

- [ ] **步骤 5：Commit**

```bash
git add tests/ && git commit -m "test(metrics): 12 类批次指标回归（命中率/证据/状态分布）"
```

---

## 里程碑 M6 — 报销层级与交付（22–26）

### 任务 22：报销包 fixtures 端到端（4 种组合 + 无分节降级 + 非子类型回归）

**文件：**
- 创建：`tests/fixtures/{reimburse_travel,reimburse_hospitality,reimburse_office,reimburse_incomplete,reimburse_nosection}.json`；扩展 `tests/test_pipeline.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_pipeline.py（追加）
def test_travel_package(rules):
    c = classify_doc(_load(str(FIX / "reimburse_travel.json")), rules, llm=None)
    assert c.subtype == "travel_expense" and c.status == "classified"
    assert c.category_path == ["报销", "差旅费报销", "张三"]

def test_hospitality_package(rules):
    c = classify_doc(_load(str(FIX / "reimburse_hospitality.json")), rules, llm=None)
    assert c.subtype == "hospitality" and c.category_path == ["报销", "业务招待费报销", "张三"]

def test_office_package(rules):
    c = classify_doc(_load(str(FIX / "reimburse_office.json")), rules, llm=None)
    assert c.subtype == "office_supplies" and c.category_path == ["报销", "办公用品报销", "张三"]

def test_incomplete_package_review(rules):        # 成功标准 #5：required 缺失 → review 不误判
    c = classify_doc(_load(str(FIX / "reimburse_incomplete.json")), rules, llm=None)
    assert c.status == "review" and c.subtype is None and c.category_path == ["报销"]

def test_nosection_degraded(rules):              # 审查重点 #4
    c = classify_doc(_load(str(FIX / "reimburse_nosection.json")), rules, llm=None)
    assert c.subtype == "travel_expense"         # 全文降级检测仍能判对
    assert any(e.source == "material" for e in c.evidence)

def test_non_subtype_doc_unchanged(rules):       # v1.1 行为回归（design 4.6）
    c = classify_doc(_load(str(FIX / "contract.json")), rules, llm=None)
    assert c.subtype is None and c.category_path == ["合同", "阿里巴巴（中国）有限公司"]
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_pipeline.py -q`
预期：5 failed（fixture 不存在）+ 1 passed（contract 回归）

- [ ] **步骤 3：实现 5 份报销包 fixtures（多 sections，首页恒为审批单）**

- `reimburse_travel`：sections = [审批单（`报销单 报销人：张三 部门：财务部 审批通过`）、发票（`增值税普通发票 发票号码 价税合计 购方名称：阿里巴巴（中国）有限公司 税号：9133…`）、行程单（`行程单 登机牌 北京-上海`）、住宿（`住宿 酒店 房费`）] → materials ⊇ {approval, invoice, itinerary, hotel} → travel 5 > office 4；
- `reimburse_hospitality`：[审批单、发票、餐费单（`餐费单 餐饮 800元 菜单`）] → hospitality 6 > office 4；
- `reimburse_office`：[审批单、发票] → office 4，唯一候选；
- `reimburse_incomplete`：[审批单（`报销单 报销人：张三 审批`）、餐费单（`餐费单 餐饮 800元`）] → materials {approval, meal} → 各 option required 不全（都缺 invoice）→ 无候选 → review。**首页必须是审批单**：若只有发票页，首分节/全文会命中 `invoice` 文档类型（发票/价税合计 2 词），不再进入报销分支；
- `reimburse_nosection`：**`sections: null`**，text 为差旅包全文拼接（**不含 `税号` 行**，避免全文判定下 reimbursement/invoice 并列 → review）→ 全文降级检测仍判 travel。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_pipeline.py -q`
预期：全部 passed（成功标准 #5 成立）

- [ ] **步骤 5：Commit**

```bash
git add tests/fixtures/ tests/test_pipeline.py && git commit -m "feat(fixtures): 报销包 e2e（4 组合 + 无分节降级 + 非子类型回归）"
```

### 任务 23：材料/报销类型全配置化回归（不改代码，只加 YAML）

**文件：**
- 创建：`tests/fixtures/rules_reimburse_ext.yaml`、`tests/fixtures/reimburse_telecom.json`、`tests/test_config_driven.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_config_driven.py
from doc_classifier.config import load_rules
from doc_classifier.pipeline import classify_doc

def test_telecom_expense_config_only():
    # 不改任何引擎代码：扩展 YAML 新增材料 telecom_bill + 报销类型 telecom_expense
    rules = load_rules(str(FIX / "rules_reimburse_ext.yaml"))
    doc = _load(str(FIX / "reimburse_telecom.json"))
    c = classify_doc(doc, rules, llm=None)
    assert c.subtype == "telecom_expense"
    assert c.category_path == ["报销", "通讯费报销", "张三"]
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_config_driven.py -q`
预期：FAIL（FileNotFoundError）

- [ ] **步骤 3：实现（仅数据文件，验证零代码改动）**

`rules_reimburse_ext.yaml`：复制包内 rules.yaml，在 `reimbursement.subtypes` 追加 `materials.telecom_bill: {display: 通讯费单, keywords: [话费, 通讯费, 月租]}` 与 `options.telecom_expense: {display: 通讯费报销, required: [invoice, telecom_bill], dimensions: [{use: person_name, priority: 1}]}`。
`reimburse_telecom.json`：sections = [审批单（报销人：张三）、发票、通讯费单（`本月话费 通讯费 100 元 月租`）]。
**自检**：`git diff` 必须只显示 `tests/` 下新增文件，`doc_classifier/` 源码零改动。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_config_driven.py -q`
预期：1 passed（成功标准 #6 成立）

- [ ] **步骤 5：Commit**

```bash
git add tests/ && git commit -m "test(config): 材料/报销类型全配置化回归（telecom，零代码改动）"
```

### 任务 24：换规则不改代码回归（维度切换，成功标准 #4）

**文件：**
- 创建：`tests/fixtures/rules_alt.yaml`；扩展 `tests/test_config_driven.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_config_driven.py（追加）
def test_dimension_switch_config_only():
    # 同一份合同，改用 person_name 主维度 → 路径随之改变，零代码改动
    rules = load_rules(str(FIX / "rules_alt.yaml"))
    doc = _load(str(FIX / "contract.json"))
    c = classify_doc(doc, rules, llm=None)
    assert c.dimension == "person_name" and c.category_path[0] == "合同"
    assert c.category_path[1] != "阿里巴巴（中国）有限公司"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest tests/test_config_driven.py -q`
预期：FAIL（FileNotFoundError）

- [ ] **步骤 3：实现（仅数据文件）**

`rules_alt.yaml`：复制包内 rules.yaml，仅改 `contract.dimensions: [{use: person_name, priority: 1}, {use: party_a_name, priority: 2}]`；`contract.json` 文本含 `联系人：张三`（确认现有 fixture 有，无则补一行）。`git diff` 自检：引擎源码零改动。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest tests/test_config_driven.py -q`
预期：2 passed（成功标准 #4 成立）

- [ ] **步骤 5：Commit**

```bash
git add tests/ && git commit -m "test(config): 维度切换回归（rules_alt，零代码改动）"
```

### 任务 25：文档（README + rules_guide 全字段说明）

**文件：**
- 创建：`README.md`、`doc_classifier/docs/rules_guide.md`

- [ ] **步骤 1：编写 README 并验证可复现**

`README.md`：安装（venv + requirements）、CLI 用法（含可直接复制运行的命令：`python -m doc_classifier.cli --rules doc_classifier/rules.yaml --input docs.jsonl --output out.jsonl`）、JSONL 输入输出 schema 示例、集成到识别流水线的方式（`classify_doc` API）、LLM 开关与合规说明（`llm:` 块 + `DOC_CLASSIFIER_LLM` env）、验证命令（`pytest -q`）。
- 验证：在干净 shell 中按 README 逐条执行命令，全部成功。

- [ ] **步骤 2：编写 `doc_classifier/docs/rules_guide.md`**

rules.yaml 全字段说明（version/llm/dimensions（含 labels/threshold/llm_fallback）/document_types（detect 计分语义、dimensions、subtypes.materials/options/权重）/unknown_policy）+ 扩展清单（新增维度/材料/报销类型/标签各一步）+ 已知歧义（发票抬头购/销方、单页报销单逃生口 option、2 字人名置信度规则）+ 扩展方向（日期/项目编号/资产编号 extractor 预留）。
- 验证：指南中每个字段名与 `config.py` schema 一一对应（人工核对清单）。

- [ ] **步骤 3：Commit**

```bash
git add README.md doc_classifier/docs/rules_guide.md && git commit -m "docs: README + rules 编写指南"
```

### 任务 26：代码审查与收尾（两阶段审查 + 全量回归）

**文件：**
- 创建：`review.md`、`final_report.md`

- [ ] **步骤 1：阶段一 —— 规范符合性审查**

对照 `design.md` v1.4 逐节核对实现（4.1 流水线/4.3 契约与三组钉死规则/4.4 schema/4.6 状态语义与首分节规则/6 成功标准 7 条）；`Critical/Major/Minor` 分级记录到 `review.md`，Critical 必须修复后重跑。

- [ ] **步骤 2：阶段二 —— 代码质量审查**

对照本 plan 的「全局约束」「审查重点」6 条 + 各任务步骤检查实现（命名/重复代码/正则可读性/测试断言是否被弱化）；结果追加 `review.md`。

- [ ] **步骤 3：全量回归 + 收尾报告**

运行：`.venv/bin/python -m pytest tests/ -q`
预期：全量 passed，Critical = 0。撰写 `final_report.md`（交付物清单、成功标准 1-7 逐条达成证据、遗留事项）。

- [ ] **步骤 4：Commit**

```bash
git add review.md final_report.md && git commit -m "chore: 两阶段审查 + 收尾报告"
```

---

## 依赖关系图

```
1 ─┬→ 2 ─┬→ 5/6/7/8（可并行）──────────────────────┐
     │        └→ 9 ─┬→ 11 ────────────────────────────────┐ │
     └→ 3 → 4      └→ 10 ───────────────────────────────┤ │
          │      11 需 9+10                              │ │
          └→ 12 → 13 ───────────────────────────────────┐  │ │
                                                           ├─→ 14 → 15 → 16
                                                           │        ↓
     3 → 17/18/19（可并行）→ 20 → 21 ─────────────┘        │
                                                                   ├→ 22 → 23
     15/16 → 24（可并行于 22）──────────────────────────────┘   ↓
     全部 → 25 → 26
```

## 批量执行建议（Subagent）

| 批次 | 任务 | 说明 |
|---|---|---|
| 1 | 1–4 | 骨架 + 模型 + 配置 + rules.yaml（串行） |
| 2 | 5–8 | 四个抽取器（相互独立，可并行） |
| 3 | 9–13 | 9/10/12 并行 → 11 → 13 |
| 4 | 14–16 | 编排 → CLI → 业务 fixtures（串行） |
| 5 | 17–21 | 三个抽取器并行 → 20 → 21 |
| 6 | 22–24 | 22 → 23；24 可与 22 并行 |
| 7 | 25–26 | 文档 → 两阶段审查收尾 |

> 每批结束设人工检查点：`.venv/bin/python -m pytest tests/ -q` 全绿 + 与本 plan/design 一致后再进入下一批。
> 时间估算仅供参考：每任务含完整 TDD 循环 + commit，实际 15–40 分钟/任务，**不作为硬性检查点**。

