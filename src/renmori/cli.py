"""
renmori command-line interface.

    renmori protect <game-build-dir> [-o OUTPUT] [options]
    renmori verify  <protected-dir>

`protect` takes a built Ren'Py 8.x distribution (a directory containing
``game/``), packs everything under ``game/`` into an encrypted container,
transforms compiled scripts, removes the plaintext originals, and drops in the
loader extension. `verify` re-checks a protected build against its manifest
(useful as a CI assertion).

Exit codes: 0 success; 2 usage / precondition error; 1 runtime failure.

This is the open-core BASELINE pipeline: fixed format, placeholder key handling.
The closed binary plugin replaces key derivation and adds per-build polymorphism.
"""

import argparse
import fnmatch
import hashlib
import json
import os
import pathlib
import shutil
import sys
import zipfile

from . import __version__
from .container import DEFAULT_CHUNK_SIZE, ContainerWriter, normalize_name
from .script import SCRIPT_EXTENSIONS, transform_rpyc

CONTAINER_NAME = "renmori.rmc"
EXTENSION_NAME = "renmori.rpe"
MANIFEST_NAME = "renmori-manifest.json"
CONFIG_NAME = "renmori.toml"

# Never packed: runtime-written dirs, and renmori's own artifacts.
SKIP_TOP_DIRS = {"saves", "cache"}
SKIP_FILES = {CONTAINER_NAME, EXTENSION_NAME}

# Files read OUTSIDE renpy.loader (by the Steam SDK or the native launcher), so
# they must stay as plaintext on disk. Kept unencrypted by default; add more via
# the `keep_on_disk` config key. See docs/m4.md.
DEFAULT_KEEP_ON_DISK = ["steam_appid.txt"]

SUPPORTED_STRENGTHS = {"baseline"}

EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_USAGE = 2


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="renmori",
        description="Protect a built Ren'Py game.",
        epilog="Exit codes: 0 success, 2 usage/precondition error, 1 runtime failure.",
    )
    parser.add_argument("--version", action="version", version="renmori " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("protect", help="protect a built Ren'Py game directory")
    p.add_argument("game_dir", help="built game directory (contains 'game/')")
    p.add_argument("-o", "--output", help="output directory (default: protect in place)")
    p.add_argument("-c", "--config", help="path to renmori.toml (default: autodetect)")
    p.add_argument("--chunk-size", type=int, default=None, help="container chunk size in bytes")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="glob of game-relative paths to leave unencrypted (repeatable)")
    p.add_argument("--strength", default=None, help="protection strength (open tool: 'baseline')")
    p.add_argument("--no-lockdown", dest="lockdown", action="store_false", default=None,
                   help="do not disable console/developer/export in the build")
    p.add_argument("--keep-plaintext", action="store_true", help="don't delete packed originals (debug)")
    p.add_argument("--quiet", action="store_true", help="only emit the final JSON result")
    p.set_defaults(func=cmd_protect)

    v = sub.add_parser("verify", help="check a protected build against its manifest")
    v.add_argument("protected_dir", help="a directory produced by 'renmori protect'")
    v.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


_QUIET = False


def _log(msg):
    if not _QUIET:
        print(msg, file=sys.stderr)


def _fail(msg, code=EXIT_USAGE):
    print("error: " + msg, file=sys.stderr)
    print(json.dumps({"status": "error", "message": msg}))
    return code


# --- config ---------------------------------------------------------------

def _load_toml(path):
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # fallback
        except ModuleNotFoundError:
            raise RuntimeError(
                "reading %s needs Python 3.11+ or the 'tomli' package" % path.name
            )
    with open(path, "rb") as f:
        return tomllib.load(f)


def _resolve_config(args, src_root):
    """Merge config file + CLI into a settings dict. CLI wins; --exclude extends."""
    cfg_path = None
    if args.config:
        cfg_path = pathlib.Path(args.config)
        if not cfg_path.is_file():
            raise RuntimeError("config not found: %s" % cfg_path)
    else:
        for cand in (src_root / CONFIG_NAME, pathlib.Path.cwd() / CONFIG_NAME):
            if cand.is_file():
                cfg_path = cand
                break

    file_cfg = {}
    if cfg_path is not None:
        data = _load_toml(cfg_path)
        file_cfg = data.get("protect", {})
        file_cfg["_keys"] = data.get("keys", {})
        _log("using config %s" % cfg_path)

    keys = file_cfg.get("_keys", {})
    excludes = (
        list(DEFAULT_KEEP_ON_DISK)
        + list(file_cfg.get("keep_on_disk", []))
        + list(file_cfg.get("exclude", []))
        + list(args.exclude)
    )

    settings = {
        "chunk_size": args.chunk_size or file_cfg.get("chunk_size", DEFAULT_CHUNK_SIZE),
        "exclude": excludes,
        "strength": args.strength or file_cfg.get("strength", "baseline"),
        "lockdown": args.lockdown if args.lockdown is not None else file_cfg.get("lockdown", True),
        "keep_plaintext": args.keep_plaintext or file_cfg.get("keep_plaintext", False),
        "master_env": keys.get("master_env"),
        "script_env": keys.get("script_env"),
    }
    return settings


def _key_from_env(var):
    """Return a 32-byte key from a hex env var, or a fresh random key if unset."""
    if not var:
        return os.urandom(32), "random"
    raw = os.environ.get(var)
    if not raw:
        _log("note: %s not set; using a random key" % var)
        return os.urandom(32), "random"
    try:
        key = bytes.fromhex(raw.strip())
    except ValueError:
        raise RuntimeError("%s must be hex" % var)
    if len(key) != 32:
        raise RuntimeError("%s must be 32 bytes (64 hex chars), got %d" % (var, len(key)))
    return key, "env:" + var


# --- protect ---------------------------------------------------------------

def cmd_protect(args):
    global _QUIET
    _QUIET = args.quiet

    src_root = pathlib.Path(args.game_dir).resolve()
    game_dir = src_root / "game"

    if not game_dir.is_dir():
        return _fail("%s has no 'game/' directory" % src_root)
    if (game_dir / CONTAINER_NAME).exists():
        return _fail("%s is already protected (found %s)" % (src_root, CONTAINER_NAME))

    try:
        settings = _resolve_config(args, src_root)
    except RuntimeError as e:
        return _fail(str(e))

    if settings["strength"] not in SUPPORTED_STRENGTHS:
        return _fail("strength %r requires the closed renmori plugin; open tool supports 'baseline'"
                     % settings["strength"])

    try:
        master_key, master_src = _key_from_env(settings["master_env"])
        script_key, script_src = _key_from_env(settings["script_env"])
    except RuntimeError as e:
        return _fail(str(e))

    if args.output:
        out_root = pathlib.Path(args.output).resolve()
        if out_root.exists():
            return _fail("output %s already exists" % out_root)
        _log("copying %s -> %s" % (src_root, out_root))
        shutil.copytree(src_root, out_root)
    else:
        out_root = src_root

    out_game = out_root / "game"
    excludes = settings["exclude"]

    to_pack, excluded = _partition(out_game, excludes)
    if not to_pack:
        return _fail("nothing to pack under %s" % out_game)

    container_path = out_game / CONTAINER_NAME
    manifest_files = []
    script_count = 0

    _log("packing %d files (%d excluded) into %s" % (len(to_pack), len(excluded), container_path.name))
    try:
        with ContainerWriter(str(container_path), master_key, chunk_size=settings["chunk_size"]) as w:
            for abs_path, rel_name in to_pack:
                if rel_name.lower().endswith(SCRIPT_EXTENSIONS):
                    w.add_bytes(rel_name, transform_rpyc(abs_path.read_bytes(), script_key))
                    script_count += 1
                else:
                    w.add_file(rel_name, str(abs_path))
                manifest_files.append({"name": rel_name, "size": abs_path.stat().st_size})
    except Exception as e:  # noqa: BLE001
        return _fail("packing failed: %s" % e, EXIT_RUNTIME)

    _log("transformed %d script files; keys: master=%s script=%s" % (script_count, master_src, script_src))

    if not settings["keep_plaintext"]:
        _remove_packed(out_game, to_pack)

    _write_extension(out_game / EXTENSION_NAME, master_key, script_key, settings["lockdown"])
    manifest = _write_manifest(out_root, container_path, manifest_files, settings)

    _log("done: %d files protected, container %d bytes" % (len(manifest_files), container_path.stat().st_size))
    _log("output: %s" % out_root)
    print(json.dumps({"status": "ok", "output": str(out_root), "manifest": manifest}))
    return EXIT_OK


def _excluded(rel_name, patterns):
    return any(fnmatch.fnmatch(rel_name, pat) for pat in patterns)


def _partition(game_dir, excludes):
    """Return (to_pack, excluded) lists of (abs_path, rel_name)."""
    to_pack, excluded = [], []
    for dirpath, dirnames, filenames in os.walk(game_dir):
        rel_dir = os.path.relpath(dirpath, game_dir)
        top = (rel_dir.split(os.sep, 1)[0]) if rel_dir != "." else ""
        if top in SKIP_TOP_DIRS:
            dirnames[:] = []
            continue
        for fn in filenames:
            if rel_dir == "." and fn in SKIP_FILES:
                continue
            abs_path = pathlib.Path(dirpath) / fn
            if abs_path.is_symlink() or not abs_path.is_file():
                continue
            rel_name = normalize_name(os.path.relpath(abs_path, game_dir))
            (excluded if _excluded(rel_name, excludes) else to_pack).append((abs_path, rel_name))
    return to_pack, excluded


def _remove_packed(game_dir, to_pack):
    for abs_path, _ in to_pack:
        try:
            abs_path.unlink()
        except OSError as e:
            _log("warning: could not remove %s: %s" % (abs_path, e))
    for dirpath, dirnames, filenames in os.walk(game_dir, topdown=False):
        if pathlib.Path(dirpath) == game_dir:
            continue
        try:
            next(os.scandir(dirpath))
        except StopIteration:
            os.rmdir(dirpath)
        except OSError:
            pass


# Modules copied into the renmori_rt package inside the .rpe (stdlib + ctypes).
_RT_MODULES = {
    "renmori_rt/format.py": ("container", "format.py"),
    "renmori_rt/crypto.py": ("container", "crypto.py"),
    "renmori_rt/reader.py": ("container", "reader.py"),
    "renmori_rt/hook.py": ("runtime", "hook.py"),
}

_AUTORUN = '''# renmori runtime extension - autogenerated, BASELINE build. Do not edit.
import os
import renpy
import renmori_rt.hook as hook

# BASELINE PLACEHOLDER KEYS. The closed runtime derives these at run time and
# stores no plaintext key on disk. These hex literals are the exact thing the
# closed key-derivation logic replaces; do not ship a real title like this.
_KEY = bytes.fromhex("{key_hex}")
_SCRIPT_KEY = bytes.fromhex("{script_key_hex}")

hook.install(
    os.path.join(renpy.config.gamedir, {container!r}),
    _KEY,
    script_key=_SCRIPT_KEY,
    lockdown={lockdown!r},
)
'''


def _write_extension(path, master_key, script_key, lockdown):
    pkg_root = pathlib.Path(__file__).resolve().parent
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("autorun.py", _AUTORUN.format(
            key_hex=master_key.hex(), script_key_hex=script_key.hex(),
            container=CONTAINER_NAME, lockdown=bool(lockdown)))
        z.writestr("renmori_rt/__init__.py", "")
        for arc, (subdir, fn) in _RT_MODULES.items():
            z.writestr(arc, (pkg_root / subdir / fn).read_text(encoding="utf-8"))
    _log("wrote loader extension %s (lockdown=%s)" % (path.name, bool(lockdown)))


def _write_manifest(out_root, container_path, files, settings):
    sha = hashlib.sha256(container_path.read_bytes()).hexdigest()
    manifest = {
        "renmori_version": __version__,
        "container_format": 1,
        "strength": settings["strength"],
        "chunk_size": settings["chunk_size"],
        "lockdown": bool(settings["lockdown"]),
        "container_sha256": sha,
        "container_bytes": container_path.stat().st_size,
        "file_count": len(files),
        "files": sorted(files, key=lambda e: e["name"]),
    }
    (out_root / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"file_count": len(files), "container_sha256": sha, "strength": settings["strength"]}


# --- verify ----------------------------------------------------------------

def cmd_verify(args):
    root = pathlib.Path(args.protected_dir).resolve()
    manifest_path = root / MANIFEST_NAME
    game = root / "game"

    if not manifest_path.is_file():
        return _fail("no %s in %s" % (MANIFEST_NAME, root))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems = []

    container = game / CONTAINER_NAME
    extension = game / EXTENSION_NAME
    if not container.is_file():
        problems.append("missing %s" % CONTAINER_NAME)
    if not extension.is_file():
        problems.append("missing %s" % EXTENSION_NAME)

    if container.is_file():
        sha = hashlib.sha256(container.read_bytes()).hexdigest()
        if sha != manifest.get("container_sha256"):
            problems.append("container sha mismatch")

    # No plaintext scripts/archives should remain on disk.
    for p in game.rglob("*"):
        if p.suffix in (".rpa", ".rpyc", ".rpy", ".rpyb") and "cache" not in p.parts and p.is_file():
            problems.append("plaintext left: %s" % p.relative_to(root))
            break

    if problems:
        print(json.dumps({"status": "error", "problems": problems}))
        for p in problems:
            _log("verify: " + p)
        return EXIT_RUNTIME

    result = {"status": "ok", "file_count": manifest.get("file_count"),
              "container_sha256": manifest.get("container_sha256")}
    _log("verify: ok (%s files, container sha %s…)" % (
        manifest.get("file_count"), str(manifest.get("container_sha256"))[:12]))
    print(json.dumps(result))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
