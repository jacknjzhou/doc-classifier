"""测试共享 fake（LLM 客户端）。"""

from __future__ import annotations

VALID = '{"person_name": {"value": "张三", "span": [3, 5], "confidence": 0.8}}'


class FakeClient:
    def __init__(self, reply=VALID, fail=False):
        self.reply = reply
        self.fail = fail
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        if self.fail:
            raise TimeoutError("boom")

        class R:
            content = self.reply

        return R()
