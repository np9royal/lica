"""Decision pack schema: YAML documents describing typed questions and verdict rules."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

PACK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")


class Action(str, Enum):
    """What a hook should do with the event."""

    ALLOW = "allow"
    BLOCK = "block"
    ASK = "ask"
    LOG = "log"


class HookPoint(str, Enum):
    """Agent-agnostic lifecycle points. Adapters map native names onto these."""

    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    USER_PROMPT = "user_prompt"
    PRE_COMPACT = "pre_compact"
    NOTIFICATION = "notification"
    STOP = "stop"

    @classmethod
    def parse(cls, value: str) -> HookPoint:
        key = re.sub(r"[_\-\s]", "", str(value)).lower()
        if key in _HOOK_ALIASES:
            return _HOOK_ALIASES[key]
        for point in cls:
            if key == point.value.replace("_", ""):
                return point
        raise ValueError(f"unknown hook point {value!r}")


_HOOK_ALIASES: dict[str, HookPoint] = {
    "pretooluse": HookPoint.PRE_TOOL_CALL,
    "pretoolcall": HookPoint.PRE_TOOL_CALL,
    "posttooluse": HookPoint.POST_TOOL_CALL,
    "posttoolcall": HookPoint.POST_TOOL_CALL,
    "userpromptsubmit": HookPoint.USER_PROMPT,
    "userprompt": HookPoint.USER_PROMPT,
    "precompact": HookPoint.PRE_COMPACT,
    "notification": HookPoint.NOTIFICATION,
    "stop": HookPoint.STOP,
    "subagentstop": HookPoint.STOP,
}


class Question(BaseModel):
    """One typed question handed to the decision model."""

    type: Literal["choice", "score", "noul"]
    instructions: str
    criteria: dict[str, str | None] | list[str] | None = None

    @model_validator(mode="after")
    def _check_criteria(self) -> Question:
        if self.type == "choice":
            if not isinstance(self.criteria, dict) or not self.criteria:
                raise ValueError(
                    "choice questions require a non-empty criteria map {option: description}"
                )
            if len(self.criteria) > 255:
                raise ValueError("choice questions support at most 255 options")
        elif self.type == "score":
            if not isinstance(self.criteria, list) or not (2 <= len(self.criteria) <= 10):
                raise ValueError("score questions require a criteria list of 2-10 ordered levels")
        return self

    def to_laya(self) -> dict[str, Any]:
        """Render in the shape Laya's Router.predict expects."""
        q: dict[str, Any] = {"type": self.type, "instructions": self.instructions}
        if self.criteria is not None:
            q["criteria"] = self.criteria
        return q


class Match(BaseModel):
    """Which tools a pack applies to. Glob-style: '*' or prefix match 'mcp__*'."""

    tools: list[str] = Field(default_factory=lambda: ["*"])

    def matches(self, tool_name: str) -> bool:
        for pat in self.tools:
            if pat == "*":
                return True
            if pat.endswith("*"):
                if tool_name.startswith(pat[:-1]):
                    return True
            elif tool_name == pat:
                return True
        return False


class Condition(BaseModel):
    """A comparison against one question's answer."""

    model_config = ConfigDict(populate_by_name=True)

    question: str
    eq: Any | None = None
    gte: float | None = None
    lte: float | None = None
    in_: list[Any] | None = Field(default=None, alias="in")


class Rule(BaseModel):
    """Either `if: {...} / action` or a terminal `default: <action>`."""

    model_config = ConfigDict(populate_by_name=True)

    condition: Condition | None = Field(default=None, alias="if")
    default: Action | None = None
    action: Action | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _check_form(self) -> Rule:
        if self.default is not None:
            if self.condition is not None or self.action is not None:
                raise ValueError("a `default` rule takes only an optional `reason`")
        elif self.condition is None or self.action is None:
            raise ValueError("a non-default rule requires both `if` and `action`")
        return self

    @property
    def resolved_action(self) -> Action:
        return self.default if self.default is not None else self.action  # type: ignore[return-value]


class Pack(BaseModel):
    """A complete decision pack document."""

    pack: str = Field(pattern=PACK_NAME_RE.pattern)
    version: str = "0.0.0"
    description: str = ""
    hooks: list[HookPoint]
    match: Match = Field(default_factory=Match)
    model: str | None = None
    max_len: int | None = Field(default=None, gt=0)
    state_template: str
    questions: dict[str, Question]
    decision: list[Rule]

    @field_validator("hooks", mode="before")
    @classmethod
    def _normalize_hooks(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [HookPoint.parse(x) for x in v]
        return v

    @model_validator(mode="after")
    def _check_decision(self) -> Pack:
        if not self.decision:
            raise ValueError("pack needs at least one decision rule")
        seen_default = False
        for i, rule in enumerate(self.decision):
            if rule.default is not None:
                if i != len(self.decision) - 1:
                    raise ValueError("`default` rule must be the last rule")
                seen_default = True
                continue
            cond = rule.condition
            assert cond is not None
            if cond.question not in self.questions:
                raise ValueError(f"rule references unknown question {cond.question!r}")
            q = self.questions[cond.question]
            if q.type == "choice" and cond.eq is not None and cond.eq not in (q.criteria or {}):
                raise ValueError(
                    f"rule eq={cond.eq!r} is not an option of choice question {cond.question!r}"
                )
            if q.type == "noul" and cond.eq is not None and not isinstance(cond.eq, bool):
                raise ValueError("noul conditions use gte/lte, or eq against a boolean")
        if not seen_default and not self.decision:
            raise ValueError("pack needs a decision list")
        return self

    def questions_for_laya(self) -> dict[str, Any]:
        return {name: q.to_laya() for name, q in self.questions.items()}

    @classmethod
    def from_yaml(cls, text: str, source: str = "<string>") -> Pack:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError(f"invalid pack {source}: expected a YAML mapping")
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise ValueError(f"invalid pack {source}: {e}") from e
