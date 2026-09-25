from fastapi.testclient import TestClient

from lica.config import Config
from lica.packs.loader import load_packs
from lica.server import create_app


class FakeRouter:
    def __init__(self, answers):
        self.answers = answers

    def predict(self, state, questions, **kw):
        return {"answers": {n: dict(self.answers.get(n, {})) for n in questions}}


def make_app(answers, config=None, tmp_path=None):
    from lica.engine import DecisionEngine

    config = config or Config()
    engine = DecisionEngine(config, router=FakeRouter(answers))
    loaded, _ = load_packs()
    packs = [lp.pack for lp in loaded.values()]
    return TestClient(create_app(config, packs, engine, project_dir=tmp_path))


def test_healthz(tmp_path):
    app = make_app({}, tmp_path=tmp_path)
    r = app.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_decide_blocks_destructive(tmp_path):
    app = make_app(
        {"blast_radius": {"score": 3.0}, "irreversible": {"noul": 0.9}},
        tmp_path=tmp_path,
    )
    r = app.post(
        "/decide",
        json={
            "hook": "pre_tool_call",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
        },
    )
    body = r.json()
    assert body["action"] == "block"
    assert body["packs"][0]["name"] == "destructive-command"
    assert "irreversible" in body["reason"]


def test_shadow_mode_returns_allow_but_records_would(tmp_path):
    config = Config()
    config.lica.mode = "shadow"
    app = make_app(
        {"blast_radius": {"score": 3.0}, "irreversible": {"noul": 0.9}},
        config=config,
        tmp_path=tmp_path,
    )
    r = app.post(
        "/decide",
        json={
            "hook": "pre_tool_call",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
        },
    )
    body = r.json()
    assert body["action"] == "allow"
    assert body["would_action"] == "block"


def test_no_matching_pack_allows(tmp_path):
    app = make_app({}, tmp_path=tmp_path)
    r = app.post("/decide", json={"hook": "stop", "tool_name": "Bash"})
    assert r.json()["action"] == "allow"


def test_unknown_hook_point_fails_per_policy(tmp_path):
    app = make_app({}, tmp_path=tmp_path)
    r = app.post("/decide", json={"hook": "bogus"})
    assert r.json()["action"] == "allow"  # default on_error


def test_decision_log_written(tmp_path):
    app = make_app({}, tmp_path=tmp_path)
    app.post("/decide", json={"hook": "post_tool_call", "tool_name": "Read", "tool_output": "x"})
    log_path = tmp_path / ".lica" / "decisions.jsonl"
    assert log_path.is_file()
    assert "post_tool_call" in log_path.read_text()
