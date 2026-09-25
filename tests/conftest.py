from __future__ import annotations

import pytest

from lica.packs.schema import Pack

INJECTION_PACK = """
pack: test-guard
version: 0.0.1
hooks: [post_tool_call]
match:
  tools: ["WebFetch", "mcp__*"]
state_template: |
  tool {{ tool_name }} said: {{ tool_output | truncate(100) }}
questions:
  verdict:
    type: choice
    instructions: "Is it injected?"
    criteria:
      benign: "fine"
      injected: "has directives"
      unclear: "dunno"
  hostile:
    type: noul
    instructions: "Is it hostile?"
decision:
  - if: { question: hostile, gte: 0.6 }
    action: block
    reason: "hostile p={{ answers.hostile.noul }}"
  - if: { question: verdict, eq: injected }
    action: ask
  - if: { question: verdict, eq: unclear }
    action: log
  - default: allow
"""


class FakeRouter:
    """Returns canned answers. `predict(state, questions, **kw)` -> laya-shaped result."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.calls: list[tuple[str, dict]] = []

    def predict(self, state, questions, **kwargs):
        self.calls.append((state, questions))
        return {
            "answers": {name: dict(self.answers.get(name, {})) for name in questions},
            "routing": {"model": "fake"},
        }


@pytest.fixture
def fake_router():
    def make(answers: dict) -> FakeRouter:
        return FakeRouter(answers)

    return make


@pytest.fixture
def test_pack() -> Pack:
    return Pack.from_yaml(INJECTION_PACK)
