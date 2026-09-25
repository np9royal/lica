import pytest

from lica.packs.loader import load_packs
from lica.packs.schema import HookPoint, Pack


def test_valid_pack_parses(test_pack):
    assert test_pack.pack == "test-guard"
    assert test_pack.hooks == [HookPoint.POST_TOOL_CALL]
    assert set(test_pack.questions) == {"verdict", "hostile"}
    assert len(test_pack.decision) == 4


def test_hook_point_aliases():
    assert HookPoint.parse("PostToolUse") is HookPoint.POST_TOOL_CALL
    assert HookPoint.parse("post_tool_call") is HookPoint.POST_TOOL_CALL
    assert HookPoint.parse("UserPromptSubmit") is HookPoint.USER_PROMPT
    assert HookPoint.parse("SubagentStop") is HookPoint.STOP
    with pytest.raises(ValueError):
        HookPoint.parse("nonsense")


def test_choice_requires_map():
    with pytest.raises(ValueError, match="choice"):
        Pack.from_yaml(
            """
pack: bad
hooks: [pre_tool_call]
state_template: x
questions:
  q: {type: choice, instructions: "i"}
decision: [{default: allow}]
"""
        )


def test_score_requires_level_list():
    with pytest.raises(ValueError, match="score"):
        Pack.from_yaml(
            """
pack: bad
hooks: [pre_tool_call]
state_template: x
questions:
  q: {type: score, instructions: "i", criteria: {a: x}}
decision: [{default: allow}]
"""
        )


def test_rule_unknown_question_rejected():
    with pytest.raises(ValueError, match="unknown question"):
        Pack.from_yaml(
            """
pack: bad
hooks: [pre_tool_call]
state_template: x
questions:
  q: {type: noul, instructions: "i"}
decision:
  - if: {question: nope, gte: 0.5}
    action: block
  - default: allow
"""
        )


def test_choice_eq_must_be_option():
    with pytest.raises(ValueError, match="not an option"):
        Pack.from_yaml(
            """
pack: bad
hooks: [pre_tool_call]
state_template: x
questions:
  q: {type: choice, instructions: "i", criteria: {a: null, b: null}}
decision:
  - if: {question: q, eq: z}
    action: block
  - default: allow
"""
        )


def test_default_must_be_last():
    with pytest.raises(ValueError, match="last"):
        Pack.from_yaml(
            """
pack: bad
hooks: [pre_tool_call]
state_template: x
questions:
  q: {type: noul, instructions: "i"}
decision:
  - default: allow
  - if: {question: q, gte: 0.5}
    action: block
"""
        )


def test_builtin_packs_load():
    loaded, errors = load_packs()
    assert errors == []
    assert {"injection-guard", "secret-leak", "destructive-command"} <= set(loaded)
    for lp in loaded.values():
        assert lp.source == "builtin"
        assert lp.pack.decision


def test_pack_name_must_be_slug():
    with pytest.raises(ValueError):
        Pack.from_yaml(
            """
pack: "Bad Name!"
hooks: [pre_tool_call]
state_template: x
questions:
  q: {type: noul, instructions: i}
decision: [{default: allow}]
"""
        )
