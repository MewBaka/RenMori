import argparse
import hashlib
import json
import os
import sys
import zipfile

import pytest

import renmori.cli as cli
from renmori.cli import main


def make_game(root, files):
    game = root / "game"
    for rel, data in files.items():
        p = game / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


def make_rpa(path, files):
    """Write a minimal RPA-3.0 archive {name: bytes}, for the unpack tests."""
    import pickle
    import zlib
    key = 0x12345678
    with open(path, "wb") as f:
        f.write(b"RPA-3.0 " + b"0" * 16 + b" %08x\n" % key)
        index = {}
        for name, data in files.items():
            off = f.tell()
            f.write(data)
            index[name] = [(off ^ key, len(data) ^ key, "")]
        ioff = f.tell()
        f.write(zlib.compress(pickle.dumps(index, 2)))
        f.seek(0)
        f.write(b"RPA-3.0 %016x %08x\n" % (ioff, key))


def _baseline(argv):
    # Baseline is now opt-in: the default strength is full protection, which needs
    # the closed plugin these open-tool tests do not have. Inject baseline for a
    # protect call that does not already set a strength.
    if argv and argv[0] == "protect" and "--strength" not in argv:
        return argv + ["--strength", "baseline"]
    return argv


def run(argv, capsys):
    rc = main(_baseline(argv))
    out = capsys.readouterr().out.strip().splitlines()
    result = json.loads(out[-1]) if out else {}
    return rc, result


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    # Never let a test reach the real plugin release. The download tests opt back
    # in with a local file:// stand-in (see the plugin_env fixture).
    monkeypatch.setenv("RENMORI_NO_DOWNLOAD", "1")
    monkeypatch.delenv("RENMORI_PLUGIN", raising=False)


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


def test_inplace_backs_up_by_default(tmp_path, capsys):
    src = make_game(tmp_path / "g", {"images/bg.png": b"\x89PNG" + b"x" * 50,
                                     "script.rpyc": b"not really rpyc"})
    rc, res = run(["protect", str(src)], capsys)
    assert rc == 0 and res["status"] == "ok"
    bak = tmp_path / "g_bak"
    assert res["backup"] == str(bak)
    # Backup holds the untouched originals; the protected dir does not.
    assert (bak / "game" / "script.rpyc").is_file()
    assert not (src / "game" / "script.rpyc").exists()
    assert (src / "game" / "renmori.rmc").is_file()


def test_inplace_refuses_when_backup_exists(tmp_path, capsys):
    src = make_game(tmp_path / "g", {"a.png": b"data"})
    (tmp_path / "g_bak").mkdir()
    rc, res = run(["protect", str(src)], capsys)
    assert rc == 2 and "already exists" in res["message"]
    assert not (src / "game" / "renmori.rmc").exists()  # nothing protected


def test_no_backup_overwrites_in_place(tmp_path, capsys):
    src = make_game(tmp_path / "g", {"a.png": b"data"})
    rc, res = run(["protect", str(src), "--no-backup"], capsys)
    assert rc == 0 and res["status"] == "ok"
    assert "backup" not in res
    assert not (tmp_path / "g_bak").exists()


def test_output_mode_makes_no_backup(tmp_path, capsys):
    src = make_game(tmp_path / "g", {"a.png": b"data"})
    rc, res = run(["protect", str(src), "-o", str(tmp_path / "p")], capsys)
    assert rc == 0 and "backup" not in res
    assert not (tmp_path / "g_bak").exists()


def test_quiet_emits_only_json(tmp_path, capsys):
    src = make_game(tmp_path / "g", {"a.png": b"data", "s.rpyc": b"rpyc"})
    rc = main(_baseline(["protect", str(src), "-o", str(tmp_path / "p"), "--quiet"]))
    cap = capsys.readouterr()
    assert rc == 0
    assert cap.err == ""  # no styled output on stderr
    lines = cap.out.strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["status"] == "ok"


def test_lang_zh_localizes_stderr_only(tmp_path, capsys):
    src = make_game(tmp_path / "g", {"a.png": b"data"})
    rc = main(_baseline(["protect", str(src), "-o", str(tmp_path / "p"), "--lang", "zh"]))
    cap = capsys.readouterr()
    assert rc == 0
    assert "保护完成" in cap.err  # human text is Chinese
    res = json.loads(cap.out.strip().splitlines()[-1])
    assert res["status"] == "ok" and "output" in res  # JSON keys stay English


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


def test_rpa_is_unpacked(tmp_path, capsys):
    # a game whose files live inside a .rpa must be unpacked into the container,
    # not packed as an opaque blob (else the engine cannot find them)
    src = tmp_path / "g"
    (src / "game").mkdir(parents=True)
    make_rpa(str(src / "game" / "content.rpa"), {
        "script.rpyc": b"not really rpyc",
        "images/bg.png": b"\x89PNG" + b"x" * 50,
    })
    out = tmp_path / "out"
    rc, res = run(["protect", str(src), "-o", str(out)], capsys)
    assert rc == 0
    assert not (out / "game" / "content.rpa").exists()
    names = {e["name"] for e in json.loads((out / "renmori-manifest.json").read_text())["files"]}
    assert "script.rpyc" in names and "images/bg.png" in names
    assert "content.rpa" not in names


def _zip_build(zpath, files, top=None):
    """Zip a game build {game-relative: bytes}, optionally wrapped in a top folder
    like a real Ren'Py distribution."""
    with zipfile.ZipFile(zpath, "w") as z:
        for rel, data in files.items():
            arc = ("game/" + rel) if top is None else (top + "/game/" + rel)
            z.writestr(arc, data)


def test_zip_input_is_extracted(tmp_path, capsys):
    # a .rpa inside the zip must still be unpacked, exercising the whole path
    make_rpa(str(tmp_path / "content.rpa"), {"script.rpyc": b"not really rpyc"})
    zpath = tmp_path / "MyGame-1.0-pc.zip"
    _zip_build(zpath, {"content.rpa": (tmp_path / "content.rpa").read_bytes(),
                       "images/bg.png": b"\x89PNG" + b"x" * 50}, top="MyGame-1.0-pc")
    out = tmp_path / "out"
    rc, res = run(["protect", str(zpath), "-o", str(out)], capsys)
    assert rc == 0 and res["status"] == "ok"
    assert (out / "game" / "renmori.rmc").is_file()
    assert (out / "game" / "renmori.rpe").is_file()
    assert not (out / "game" / "content.rpa").exists()
    names = {e["name"] for e in json.loads((out / "renmori-manifest.json").read_text())["files"]}
    assert "script.rpyc" in names and "images/bg.png" in names
    # the original archive is untouched
    assert zpath.is_file()


def test_zip_input_default_output_is_sibling_folder(tmp_path, capsys):
    zpath = tmp_path / "MyGame-1.0-pc.zip"
    _zip_build(zpath, {"a.png": b"data", "s.rpyc": b"rpyc"}, top="MyGame-1.0-pc")
    rc, res = run(["protect", str(zpath)], capsys)
    assert rc == 0 and res["status"] == "ok"
    assert res["output"] == str(tmp_path / "MyGame-1.0-pc")
    assert (tmp_path / "MyGame-1.0-pc" / "game" / "renmori.rmc").is_file()
    assert "backup" not in res  # the .zip is the original; no _bak


def test_zip_input_without_top_folder(tmp_path, capsys):
    # some zips put game/ at the archive root
    zpath = tmp_path / "flat.zip"
    _zip_build(zpath, {"a.png": b"data"}, top=None)
    out = tmp_path / "out"
    rc, res = run(["protect", str(zpath), "-o", str(out)], capsys)
    assert rc == 0 and (out / "game" / "renmori.rmc").is_file()


def test_zip_without_game_dir_fails(tmp_path, capsys):
    zpath = tmp_path / "nope.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("readme.txt", b"no game here")
    rc, res = run(["protect", str(zpath), "-o", str(tmp_path / "out")], capsys)
    assert rc == 2 and res["status"] == "error"
    assert not (tmp_path / "out").exists()  # cleaned up on failure


def test_zip_input_refuses_existing_output(tmp_path, capsys):
    zpath = tmp_path / "MyGame.zip"
    _zip_build(zpath, {"a.png": b"data"}, top="MyGame")
    (tmp_path / "MyGame").mkdir()  # default output already exists
    rc, res = run(["protect", str(zpath)], capsys)
    assert rc == 2 and "already exists" in res["message"]


def test_cache_bytecode_is_packed_not_left_plaintext(tmp_path, capsys):
    # game/cache/*.rpyb is the scripts' compiled bytecode; it must be packed and
    # removed, not left in the clear. Non-sensitive cache files stay on disk.
    src = make_game(tmp_path / "g", {
        "script.rpyc": b"not really rpyc",
        "cache/bytecode-312.rpyb": b"compiled bytecode of every script",
        "cache/screens.rpyb": b"compiled screens",
        "cache/shaders.txt": b"shader1\nshader2\n",
        "cache/build_info.json": b"{}",
    })
    out = tmp_path / "p"
    rc, res = run(["protect", str(src), "-o", str(out)], capsys)
    assert rc == 0
    names = {e["name"] for e in json.loads((out / "renmori-manifest.json").read_text())["files"]}
    assert "cache/bytecode-312.rpyb" in names and "cache/screens.rpyb" in names
    assert not (out / "game" / "cache" / "bytecode-312.rpyb").exists()
    assert not (out / "game" / "cache" / "screens.rpyb").exists()
    # harmless cache files are left alone, unpacked
    assert "cache/shaders.txt" not in names
    assert (out / "game" / "cache" / "shaders.txt").is_file()
    assert (out / "game" / "cache" / "build_info.json").is_file()
    assert run(["verify", str(out)], capsys)[0] == 0


def test_verify_flags_plaintext_bytecode_in_cache(tmp_path, capsys):
    src = make_game(tmp_path / "g", {"a.png": b"a"})
    out = tmp_path / "p"
    assert run(["protect", str(src), "-o", str(out)], capsys)[0] == 0
    (out / "game" / "cache").mkdir(parents=True, exist_ok=True)
    (out / "game" / "cache" / "bytecode-312.rpyb").write_bytes(b"leaked script bytecode")
    rc, res = run(["verify", str(out)], capsys)
    assert rc == 1 and any("plaintext left" in p for p in res["problems"])


def test_default_strength_requires_plugin(tmp_path, monkeypatch):
    # default is full protection; with no plugin (and downloads off) it fails
    # rather than silently shipping the weak baseline
    monkeypatch.delenv("RENMORI_PLUGIN", raising=False)
    src = make_game(tmp_path / "g", {"script.rpyc": b"x"})
    rc = main(["protect", str(src), "-o", str(tmp_path / "p")])
    assert rc == 2


# --- plugin auto-download (against a local file:// stand-in release) ----------

def _pargs(**kw):
    ns = argparse.Namespace(plugin=None, yes=False)
    ns.__dict__.update(kw)
    return ns


def _fake_release(dirp, asset, blob):
    (dirp / asset).write_bytes(blob)
    (dirp / "SHA256SUMS").write_text("%s  %s\n" % (hashlib.sha256(blob).hexdigest(), asset))


@pytest.fixture
def plugin_env(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setenv("LOCALAPPDATA", str(cache))
    monkeypatch.delenv("RENMORI_NO_DOWNLOAD", raising=False)  # re-enable downloads
    rel = tmp_path / "release"
    rel.mkdir()
    monkeypatch.setenv("RENMORI_PLUGIN_BASE_URL", "file://" + str(rel))
    cli._QUIET, cli._LANG = False, "en"
    return rel


def test_plugin_downloads_verifies_and_caches(plugin_env):
    asset = cli._plugin_asset()
    _fake_release(plugin_env, asset, b"#!/bin/sh\necho plugin\n")
    p = cli._ensure_plugin(_pargs())
    assert p and os.path.isfile(p)
    assert open(p, "rb").read() == b"#!/bin/sh\necho plugin\n"
    assert os.access(p, os.X_OK)  # made executable
    # second call is served from cache, even with the release now gone
    (plugin_env / asset).unlink()
    (plugin_env / "SHA256SUMS").unlink()
    assert cli._ensure_plugin(_pargs()) == p


def test_plugin_download_rejects_bad_checksum(plugin_env):
    asset = cli._plugin_asset()
    (plugin_env / asset).write_bytes(b"real bytes")
    (plugin_env / "SHA256SUMS").write_text("%s  %s\n" % ("00" * 32, asset))
    assert cli._ensure_plugin(_pargs()) is None
    assert not (plugin_env.parent / "cache").exists() or not list((plugin_env.parent / "cache").rglob(asset))


def test_plugin_no_download_env_disables_fetch(plugin_env, monkeypatch):
    _fake_release(plugin_env, cli._plugin_asset(), b"x")
    monkeypatch.setenv("RENMORI_NO_DOWNLOAD", "1")
    assert cli._ensure_plugin(_pargs()) is None


def test_plugin_explicit_path_wins_over_download(plugin_env, tmp_path):
    _fake_release(plugin_env, cli._plugin_asset(), b"downloaded")
    explicit = tmp_path / "myplugin"
    explicit.write_bytes(b"explicit")
    assert cli._ensure_plugin(_pargs(plugin=str(explicit))) == str(explicit)
