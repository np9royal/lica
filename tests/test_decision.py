from lica.decision import Verdict, apply_rules, condition_holds, merge_verdicts, scalar
from lica.packs.schema import Action, Condition


def ans(type_, value):
    if type_ == "choice":
        return {"type": "choice", "choice": value, "confidence": 0.9}
    if type_ == "noul":
        return {"type": "noul", "noul": value}
    return {"type": "score", "score": value}


def test_scalar():
    assert scalar(ans("choice", "injected")) == "injected"
    assert scalar(ans("noul", 0.7)) == 0.7
    assert scalar(ans("score", 2.0)) == 2.0
    assert scalar({}) is None


def test_condition_eq_choice():
    c = Condition(question="v", eq="injected")
    assert condition_holds(c, ans("choice", "injected"))
    assert not condition_holds(c, ans("choice", "benign"))


def test_condition_gte_noul():
    c = Condition(question="h", gte=0.6)
    assert condition_holds(c, ans("noul", 0.61))
    assert not condition_holds(c, ans("noul", 0.59))


def test_condition_bool_eq_on_noul():
    c = Condition(question="h", eq=True)
    assert condition_holds(c, ans("noul", 0.9))
    assert not condition_holds(c, ans("noul", 0.2))


def test_condition_in_list():
    c = Condition(question="v", **{"in": ["a", "b"]})
    assert condition_holds(c, ans("choice", "a"))
    assert not condition_holds(c, ans("choice", "c"))


def test_threshold_override_replaces_gte():
    c = Condition(question="h", gte=0.6)
    # base bound fails at 0.5, override to 0.4 passes
    assert not condition_holds(c, ans("noul", 0.5))
    assert condition_holds(c, ans("noul", 0.5), thresholds={"h": 0.4})


def test_first_match_wins_and_default_fallback(test_pack):
    answers = {
        "verdict": ans("choice", "benign"),
        "hostile": ans("noul", 0.1),
    }
    v = apply_rules(test_pack, answers)
    assert v.action is Action.ALLOW
    assert v.rule_index == 3

    answers["hostile"] = ans("noul", 0.9)
    v = apply_rules(test_pack, answers)
    assert v.action is Action.BLOCK
    assert v.rule_index == 0


def test_reason_template_renders_answers(test_pack):
    answers = {"verdict": ans("choice", "benign"), "hostile": ans("noul", 0.77)}
    v = apply_rules(
        test_pack, answers, render_reason=lambda s: s.replace("{{ answers.hostile.noul }}", "0.77")
    )
    assert "0.77" in v.reason


def test_merge_prefers_block_over_ask():
    a = Verdict(Action.ASK, "a", "p1")
    b = Verdict(Action.BLOCK, "b", "p2")
    c = Verdict(Action.ALLOW, "", "p3")
    assert merge_verdicts([c, a, b]).action is Action.BLOCK
    assert merge_verdicts([c]).action is Action.ALLOW
    assert merge_verdicts([]) is None
