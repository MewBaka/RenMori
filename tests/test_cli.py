import json
import sys

import pytest

from renmori.cli import main


def make_game(root, files):
    game = root / "game"
    for rel, data in files.items():
        p = game / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


def run(argv, capsys):
    rc = main(argv)
    out = capsys.readouterr().out.strip().splitlines()
    result = json.loads(out[-1]) if out else {}
    return rc, result


def test_protect_and_verify(tmp_path, capsys):
    src = make_game(tmp_path / "g", {
        "images/bg.png": b"\x89PNG" + b"x" * 100,
        "script.rpyc": b"not really rpyc",
        "audio/m.ogg": b"OggS" + b"y" * 50,
    })
    out = tmp_path / "prot"
    rc, res = run(["protect", str(src), "-o", str(out)], capsys)
    assert rc == 0 and res["status"] == "ok"
    assert res["manifest"]["file_count"] == 3
    assert (out / "game" / "renmori.rmc").is_file()
    assert (out / "game" / "renmori.rpe").is_file()
    assert not (out / "game" / "script.rpyc").exists()  # plaintext removed

    rc, res = run(["verify", str(out)], capsys)
    assert rc == 0 and res["status"] == "ok" and res["file_count"] == 3


def test_missing_game_dir(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    rc, res = run(["protect", str(tmp_path / "empty")], capsys)
    assert rc == 2 and res["status"] == "error"


def test_already_protected(tmp_path, capsys):
    src = make_game(tmp_path / "g", {"a.png": b"data"})
    out = tmp_path / "p"
    assert run(["protect", str(src), "-o", str(out)], capsys)[0] == 0
    # Re-protecting the output must refuse.
    rc, res = run(["protect", str(out)], capsys)
    assert rc == 2 and "already protected" in res["message"]


def test_exclude(tmp_path, capsys):
    src = make_game(tmp_path / "g", {
        "keep.png": b"a", "notes.txt": b"b", "extras/readme.txt": b"c",
    })
    out = tmp_path / "p"
    rc, res = run(["protect", str(src), "-o", str(out), "--exclude", "*.txt"], capsys)
    assert rc == 0
    names = {f["name"] for f in json.loads((out / "renmori-manifest.json").read_text())["files"]}
    assert names == {"keep.png"}
    # Excluded files stay on disk unencrypted.
    assert (out / "game" / "notes.txt").is_file()
    assert (out / "game" / "extras" / "readme.txt").is_file()


def test_config_file(tmp_path, capsys):
    if sys.version_info < (3, 11):
        pytest.skip("tomllib needs 3.11+")
    src = make_game(tmp_path / "g", {"a.png": b"a", "b.txt": b"b"})
    (src / "renmori.toml").write_text(
        '[protect]\nexclude = ["*.txt"]\nlockdown = false\nchunk_size = 4096\n'
    )
    out = tmp_path / "p"
    rc, res = run(["protect", str(src), "-o", str(out)], capsys)
    assert rc == 0
    manifest = json.loads((out / "renmori-manifest.json").read_text())
    assert manifest["chunk_size"] == 4096
    assert manifest["lockdown"] is False
    names = {f["name"] for f in manifest["files"]}
    assert "b.txt" not in names


def test_key_from_env(tmp_path, capsys, monkeypatch):
    key = "11" * 32
    monkeypatch.setenv("RENMORI_TEST_MASTER", key)
    src = make_game(tmp_path / "g", {"a.png": b"a"})
    (src / "renmori.toml").write_text('[keys]\nmaster_env = "RENMORI_TEST_MASTER"\n')
    out = tmp_path / "p"
    if sys.version_info < (3, 11):
        pytest.skip("tomllib needs 3.11+")
    rc, res = run(["protect", str(src), "-o", str(out)], capsys)
    assert rc == 0 and res["status"] == "ok"


def test_bad_strength(tmp_path, capsys):
    src = make_game(tmp_path / "g", {"a.png": b"a"})
    rc, res = run(["protect", str(src), "-o", str(tmp_path / "p"), "--strength", "max"], capsys)
    assert rc == 2 and "closed renmori plugin" in res["message"]


def test_steam_appid_kept_on_disk(tmp_path, capsys):
    src = make_game(tmp_path / "g", {"a.png": b"a", "steam_appid.txt": b"480\n"})
    out = tmp_path / "p"
    rc, res = run(["protect", str(src), "-o", str(out)], capsys)
    assert rc == 0
    # Read by the Steam SDK outside renpy.loader, so it must stay on disk.
    assert (out / "game" / "steam_appid.txt").read_bytes() == b"480\n"
    names = {f["name"] for f in json.loads((out / "renmori-manifest.json").read_text())["files"]}
    assert "steam_appid.txt" not in names


def test_two_builds_are_cryptographically_independent(tmp_path, capsys):
    src = make_game(tmp_path / "g", {"a.png": b"a" * 1000, "b.ogg": b"b" * 1000})
    out1, out2 = tmp_path / "p1", tmp_path / "p2"
    assert run(["protect", str(src), "-o", str(out1)], capsys)[0] == 0
    assert run(["protect", str(src), "-o", str(out2)], capsys)[0] == 0

    def container_id(p):
        return (p / "game" / "renmori.rmc").read_bytes()[44:60]

    m1 = json.loads((out1 / "renmori-manifest.json").read_text())
    m2 = json.loads((out2 / "renmori-manifest.json").read_text())
    # Same inputs, but independent per build: different id and different bytes.
    assert container_id(out1) != container_id(out2)
    assert m1["container_sha256"] != m2["container_sha256"]
