"""
The `renmori gui` front-end. The Tk widgets need a display, so the tests cover
the pure pieces instead: the CLI-arg builder, the renmori.toml generator (it must
round-trip through a real TOML parser), the child-process command, and that the
`gui` subcommand dispatches to the launcher without opening a window.
"""

import pytest

import renmori.gui as gui
from renmori.cli import main


def test_build_protect_args_basic():
    assert gui.build_protect_args({"output": "/o", "strength": "baseline"}) == \
        ["-o", "/o", "--strength", "baseline"]


def test_build_protect_args_empty():
    assert gui.build_protect_args({}) == []


def test_build_protect_args_flags_and_lists():
    a = gui.build_protect_args({
        "platforms": "mac-universal,linux-x64", "launcher": True,
        "no_lockdown": True, "keep_plaintext": True, "no_backup": True,
        "exclude": ["a/*", "   ", "b/*"], "chunk_size": "65536",
        "plugin": "/p", "config": "/c",
    })
    assert "--launcher" in a and "--no-lockdown" in a
    assert "--no-backup" in a and "--keep-plaintext" in a
    assert a.count("--exclude") == 2  # the blank glob is dropped
    i = a.index("--platforms")
    assert a[i:i + 2] == ["--platforms", "mac-universal,linux-x64"]
    j = a.index("--chunk-size")
    assert a[j:j + 2] == ["--chunk-size", "65536"]


def test_cli_cmd_runs_renmori_module():
    assert gui._cli_cmd(["verify", "/x"])[1:] == ["-m", "renmori", "verify", "/x"]


def test_build_toml_roundtrips():
    tomllib = pytest.importorskip("tomllib")
    text = gui.build_toml({
        "strength": "auto", "lockdown": False, "chunk_size": 65536,
        "exclude": ["thirdparty/*"], "keep_on_disk": ["steam_appid.txt"],
        "platforms": ["mac-universal", "win-x64"], "launcher": True,
        "keep_plaintext": True,
        "master_env": "RENMORI_MASTER_KEY", "script_env": "RENMORI_SCRIPT_KEY",
    })
    data = tomllib.loads(text)
    assert data["protect"]["strength"] == "auto"
    assert data["protect"]["lockdown"] is False
    assert data["protect"]["chunk_size"] == 65536
    assert data["protect"]["platforms"] == ["mac-universal", "win-x64"]
    assert data["protect"]["launcher"] is True
    assert data["keys"]["master_env"] == "RENMORI_MASTER_KEY"


def test_build_toml_minimal_defaults():
    tomllib = pytest.importorskip("tomllib")
    data = tomllib.loads(gui.build_toml({}))
    assert data["protect"]["lockdown"] is True  # the one key always emitted
    assert "keys" not in data  # no [keys] section when both env names are empty


def test_gui_subcommand_dispatches(monkeypatch):
    seen = {}

    def fake_run(lang="en"):
        seen["lang"] = lang
        return 0

    monkeypatch.setattr(gui, "run", fake_run)
    assert main(["gui", "--lang", "zh"]) == 0
    assert seen["lang"] == "zh"
