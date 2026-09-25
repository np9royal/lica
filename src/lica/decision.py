"""Declarative verdict rules — no eval, no exec. First matching rule wins."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from lica.packs.schema import Action, Condition, Pack


@dataclass
class Verdict:
    action: Action
    reason: str
    pack: str
    answers: dict[str, Any] = field(default_factory=dict)
    rule_index: int | None = None
    latency_ms: float = 0.0

    @property
    def enforced(self) -> bool:
        return self.action in (Action.BLOCK, Action.ASK)


def scalar(answer: dict[str, Any]) -> Any:
    """The comparable value of a typed answer."""
    t = answer.get("type")
    if t == "choice":
        return answer.get("choice")
    if t == "score":
        return answer.get("score")
    if t == "noul":
        return answer.get("noul")
    return None


def condition_holds(
    cond: Condition, answer: dict[str, Any], thresholds: dict[str, float] | None = None
) -> bool:
    v = scalar(answer)
    if v is None:
        return False

    gte, lte = cond.gte, cond.lte
    if thresholds and cond.question in thresholds and gte is not None:
        gte = thresholds[cond.question]

    if cond.eq is not None:
        if isinstance(v, float) and isinstance(cond.eq, bool):
            if (v >= 0.5) != cond.eq:
                return False
        elif v != cond.eq:
            return False
    if gte is not None and not (float(v) >= gte):
        return False
    if lte is not None and not (float(v) <= lte):
        return False
    return cond.in_ is None or v in cond.in_


def apply_rules(
    pack: Pack,
    answers: dict[str, dict[str, Any]],
    render_reason: Callable[[str], str] = lambda s: s,
    thresholds: dict[str, float] | None = None,
) -> Verdict:
    """Walk the pack's ordered rules; return the first matching verdict."""
    for i, rule in enumerate(pack.decision):
        if rule.default is not None:
            reason = render_reason(rule.reason or "") if rule.reason else ""
            return Verdict(rule.default, reason, pack.pack, answers, i)
        cond = rule.condition
        assert cond is not None
        answer = answers.get(cond.question)
        if answer is None:
            continue
        if condition_holds(cond, answer, thresholds):
            action = rule.action or Action.ALLOW
            reason = render_reason(rule.reason or "") if rule.reason else ""
            return Verdict(action, reason, pack.pack, answers, i)
    return Verdict(Action.ALLOW, "", pack.pack, answers, None)


def merge_verdicts(verdicts: list[Verdict]) -> Verdict | None:
    """Most restrictive wins: block > ask > log > allow."""
    if not verdicts:
        return None
    order = {Action.BLOCK: 3, Action.ASK: 2, Action.LOG: 1, Action.ALLOW: 0}
    return max(verdicts, key=lambda v: order[v.action])
