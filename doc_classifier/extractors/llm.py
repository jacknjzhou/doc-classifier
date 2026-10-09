"""L2 LLM 兜底抽取器（OpenAI 兼容；每文档一次调用 + 重试降级 + 内存缓存，design 4.3）。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

from ..models import Candidate, RecognizedDoc
from .base import ExtractContext
from .registry import register_extractor

log = logging.getLogger(__name__)


class _OpenAIClient:
    """真实客户端适配器（暴露 .chat(messages) -> str，与测试 FakeClient 同形）。"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_sec: float):
        from openai import OpenAI  # 延迟导入：未启用 LLM 时零依赖开销

        self._c = OpenAI(
            base_url=base_url or None,
            api_key=api_key or "EMPTY",
            timeout=timeout_sec,
        )
        self.model = model or "gpt-4o-mini"

    def chat(self, messages: list[dict[str, str]]) -> str:
        resp = self._c.chat.completions.create(model=self.model, messages=messages)
        return resp.choices[0].message.content or ""


class LLMExtractor:
    name = "llm"

    def __init__(self, client: Any | None = None):
        self._client = client  # 测试注入点；None = 首次调用时按配置构造
        self._real: _OpenAIClient | None = None
        self.calls = 0
        self.failed = 0
        self._cache: dict[tuple, dict[str, list[Candidate]]] = {}

    # -- 开关 -------------------------------------------------------------

    def enabled(self, ctx: ExtractContext) -> bool:
        if os.environ.get("DOC_CLASSIFIER_LLM", "").lower() == "off":
            return False  # env 优先级最高（design R3）
        return ctx.rules.llm.enabled

    def _get_client(self, ctx: ExtractContext) -> _OpenAIClient:
        if self._client is not None:
            return self._client  # type: ignore[return-value]
        if self._real is None:
            cfg = ctx.rules.llm
            self._real = _OpenAIClient(
                cfg.base_url, os.environ.get(cfg.api_key_env, ""), cfg.model, cfg.timeout_sec
            )
        return self._real

    # -- 送文选择（design 4.3） --------------------------------------------

    def _pick_text(self, doc: RecognizedDoc, focus: list[int] | None) -> tuple[str, dict[str, Any] | None]:
        """返回 (送文, 映射信息)。映射信息供 span 从送文坐标换算回全文坐标。"""
        if doc.sections:
            if focus:
                idxs = sorted(set(focus))
            else:
                idxs = [0]  # 规则全未命中 → 送第一个分节
            texts = [s.text for i, s in enumerate(doc.sections) if i in idxs]
            return "\n".join(texts), {"kind": "sections", "idxs": idxs}
        return doc.text, None  # 无分节 → 全文

    # -- 主入口 -------------------------------------------------------------

    def extract_fields(
        self,
        doc: RecognizedDoc,
        fields: list[str],
        ctx: ExtractContext,
        focus: list[int] | None = None,
    ) -> dict[str, list[Candidate]]:
        empty = {f: [] for f in fields}
        if not self.enabled(ctx):
            return empty

        text, mapping = self._pick_text(doc, focus)
        key = (
            self._model_name(ctx),
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
            tuple(sorted(fields)),
        )
        if key in self._cache:
            return self._cache[key]

        raw = self._call_with_retry(ctx, text, fields)
        result: dict[str, list[Candidate]] = {}
        for f in fields:
            parsed = raw.get(f) if raw else None
            cands: list[Candidate] = []
            if parsed:
                cands = self._to_candidates(parsed, f, doc, text, mapping)
            result[f] = cands
        self._cache[key] = result
        return result

    def extract(self, doc: RecognizedDoc, field: str, ctx: ExtractContext) -> list[Candidate]:
        return self.extract_fields(doc, [field], ctx)[field]

    # -- 内部 ---------------------------------------------------------------

    @staticmethod
    def _model_name(ctx: ExtractContext) -> str:
        return ctx.rules.llm.model or "gpt-4o-mini"

    def _call_with_retry(self, ctx: ExtractContext, text: str, fields: list[str]) -> dict | None:
        client = self._get_client(ctx)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是文档信息抽取助手。只输出严格 JSON，不要输出任何其他文字。"
                    '格式：{"<字段>": {"value": 字符串, "span": [start, end], '
                    '"confidence": 0到1的小数} 或 null}，字段不存在时给 null。'
                ),
            },
            {
                "role": "user",
                "content": f"文档文本：\n{text}\n\n请抽取字段：{json.dumps(fields, ensure_ascii=False)}",
            },
        ]
        max_retries = max(0, int(ctx.rules.llm.max_retries))
        for attempt in range(max_retries + 1):
            try:
                self.calls += 1
                content = client.chat(messages)
                raw = json.loads(content)
                if not isinstance(raw, dict):
                    raise ValueError("LLM 输出不是 JSON 对象")
                return raw
            except Exception as e:  # 超时 / 5xx / 解析失败
                if attempt < max_retries:
                    continue
                self.failed += 1
                log.warning("LLM 兜底失败（重试耗尽）: %s", e)
                return None
        return None

    def _to_candidates(
        self,
        parsed: dict,
        field: str,
        doc: RecognizedDoc,
        sent_text: str,
        mapping: dict[str, Any] | None,
    ) -> list[Candidate]:
        value = parsed.get("value")
        conf = parsed.get("confidence")
        if not isinstance(value, str) or not value.strip():
            return []
        if not isinstance(conf, (int, float)):
            conf = 0.5
        span = parsed.get("span")
        span_out: tuple[int, int] | None = None
        if isinstance(span, list) and len(span) == 2 and all(isinstance(x, int) for x in span):
            s, e = span
            span_out = self._map_span(doc, sent_text, mapping, s, e)
        return [
            Candidate(value=value.strip(), field=field, confidence=float(conf), source="llm", span=span_out)
        ]

    @staticmethod
    def _map_span(
        doc: RecognizedDoc,
        sent_text: str,
        mapping: dict[str, Any] | None,
        s: int,
        e: int,
    ) -> tuple[int, int] | None:
        """把送文坐标换算回全文坐标（仅当送的是分节拼接时）。"""
        if mapping is None or not doc.sections:
            if 0 <= s <= e <= len(doc.text):
                return (s, e)
            return None
        # 逐分节定位送文内偏移
        offsets: list[tuple[int, int, int]] = []  # (送文起点, 全文起点, 长度)
        sent_off = 0
        for i in mapping["idxs"]:  # type: ignore[index]
            sec = doc.sections[i]
            off_in_full = doc.text.find(sec.text, max(0, (offsets[-1][1] + offsets[-1][2]) if offsets else 0))
            if off_in_full < 0:
                off_in_full = sent_off
            offsets.append((sent_off, off_in_full, len(sec.text)))
            sent_off += len(sec.text) + 1  # "\n".join
        for sent_start, full_start, length in offsets:
            if sent_start <= s < sent_start + length:
                gs, ge = full_start + (s - sent_start), full_start + (e - sent_start)
                gs = max(0, min(gs, len(doc.text)))
                ge = max(gs, min(ge, len(doc.text)))
                return (gs, ge)
        return None


register_extractor("llm", LLMExtractor())
