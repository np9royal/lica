from lica.config import Config, find_config, load_config


def test_defaults():
    c = Config()
    assert c.lica.mode == "enforce"
    assert c.lica.on_error == "allow"
    assert c.lica.model == "typed-decisions"


def test_load_toml(tmp_path):
    cfg_file = tmp_path / "lica.toml"
    cfg_file.write_text(
        """
[lica]
mode = "shadow"

[packs.secret-leak]
enabled = false
thresholds = { leaked = 0.8 }
""",
        encoding="utf-8",
    )
    c = load_config(cfg_file)
    assert c.lica.mode == "shadow"
    assert not c.pack_enabled("secret-leak")
    assert c.pack_enabled("injection-guard")
    assert c.pack_thresholds("secret-leak") == {"leaked": 0.8}


def test_find_config_walks_up(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    (tmp_path / "lica.toml").write_text("[lica]\nmode = 'shadow'\n")
    assert find_config(nested) == tmp_path / "lica.toml"


def test_missing_config_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = load_config()
    assert c.lica.mode == "enforce"
