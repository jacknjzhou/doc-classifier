# doc-classifier 交付报告

- 规格：`design.md` v1.4 · 计划：`plan.md`（26 任务 / 6 里程碑，TDD 逐任务 RED→GREEN）
- 审查：`review.md`（Critical 0 / Major 0 已裁决修复 / Minor 5 遗留）
- 验证：`.venv/bin/python -m pytest tests/ -q` → **87 passed**（全 mock，无网络）

## 交付物清单

```
doc_classifier/
├── models.py            # 8 数据模型（Section/RecognizedDoc/DocTypeResult/Candidate/MaterialHit/Evidence/SubtypeResult/Classification）
├── config.py            # pydantic 全量 schema + 交叉校验（维度/材料/检测器引用）
├── rules.yaml           # 默认规则：12 文档类型 / 6 维度 / 报销子类型（6 材料 3 option）/ llm 关
├── doc_type.py          # ① 关键词计分 + 标题加权 + 首分节判定域 + 并列 review
├── normalizers.py       # ③ org/person/item/topic/invoice_title 归一化 + 配置分派
├── subtype.py           # ①c required 门控 + 权重计分 + 并列不猜
├── classifier.py        # ⑤ 维度状态机 + status 钉死规则 + category_path
├── pipeline.py          # ④→⑥ 编排 + Summary（classify_doc / classify_docs）
├── cli.py               # JSONL 进出 + summary stdout + review 回流
├── extractors/          # base(Protocol) / registry / rule(5 抽取器) / llm(兜底) / material(检测器)
├── data/                # surnames.txt(100) / departments.txt(24)
└── docs/rules_guide.md  # 全字段说明 + 扩展清单 + 已知歧义
tests/                   # 15 测试文件 + 19 fixtures + conftest/util/fakes
README.md                # 安装/CLI/schema/集成/LLM 合规/扩展/验证
```

## 成功标准（design §6）逐条达成证据

| # | 标准 | 证据 |
|---|---|---|
| 1 | 12 类文档每类 ≥1 e2e fixture，核心样例命中期望路径与状态 | `tests/test_pipeline.py`：BUSINESS 3 + OFFICE 9 = 12 类全断言精确 `category_path` + `status`（12/12 通过） |
| 2 | summary 可度量：规则命中率 ≥70%、LLM 调用率 ≤30% | `tests/test_metrics.py::test_batch_metrics`：12 类批次 `rule_hit_rate == 1.0`、`llm_rate == 0.0`（LLM 关闭口径） |
| 3 | 每条结果带证据可追溯；review/unknown 进复核不落丢 | `test_batch_metrics` 断言 classified 均有 evidence；CLI 将 review/unknown 一并落盘 JSONL；材料/维度/doc_type 证据 source 区分 |
| 4 | 换 rules.yaml 改维度，零代码 | `tests/test_config_driven.py::test_dimension_switch_config_only`（rules_alt.yaml 合同换主维度，`git diff` 引擎零改动） |
| 5 | 报销层级：3 组合判对子类型 + 正确路径；required 缺失 → review | `test_travel/hospitality/office_package` + `test_incomplete_package_review`（缺 invoice → review，subtype=None） |
| 6 | 新材料+新报销类型纯配置（telecom） | `test_telecom_expense_config_only`（rules_reimburse_ext.yaml，`git diff -- doc_classifier/` 为空） |
| 7 | 核心路径单测全绿 | 87 passed（0 failed / 0 error） |

## 遗留事项（不阻塞，详见 review.md Minor-1..5）

1. person 内置默认标签与 `rules.yaml` 双源——改默认标签需同步两处。
2. LLM 多分节 span 映射为近似算法（±1 漂移，span 缺失置 None，证据链不断）。
3. LLM 超时分支无专门单测（与非法 JSON 同降级路径，已手工验证）。
4. `ItemExtractor.add` 条件式可读性待重构。
5. 材料子串匹配语义需业务侧规避跨材料词（rules_guide 已列）。

## 后续方向（design §7 之外的自然扩展）

- 词表扩充（姓氏/部门/机构）与真实语料调阈值；
- LLM 提示词按文档类型定制；`llm.enabled` 灰度开启 + `summary.llm_rate` 监控；
- 持久化层与归档落盘（引擎无状态，直接包装 `classify_docs`）。
