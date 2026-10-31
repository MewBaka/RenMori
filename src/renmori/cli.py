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

Human-facing output goes to stderr (styled, and localized to the system
language); the final line of stdout is always a machine-readable JSON object
with stable English keys, so CI piping is unaffected by styling or language.

This is the open-core BASELINE pipeline: fixed format, placeholder key handling.
The closed binary plugin replaces key derivation and adds per-build polymorphism.
"""

import argparse
import fnmatch
import hashlib
import json
import os
import pathlib
import pickle
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request
import zlib
import zipfile

from . import __version__
from .container import DEFAULT_CHUNK_SIZE, ContainerWriter, normalize_name
from .script import SCRIPT_EXTENSIONS, transform_rpyc

BRAND = "RenMori"  # display name; the command/package stays lowercase "renmori"

CONTAINER_NAME = "renmori.rmc"
EXTENSION_NAME = "renmori.rpe"
MANIFEST_NAME = "renmori-manifest.json"
CONFIG_NAME = "renmori.toml"

# Never packed: runtime-written dirs, and renmori's own artifacts. saves/ is user
# data. cache/ is Ren'Py's regenerable cache, BUT it ships the compiled bytecode
# of every script (cache/bytecode-*.rpyb, *analysis.rpyb, screens.rpyb) — leaving
# those as plaintext would hand an attacker the scripts without touching the
# container, so they are packed like any other file; the rest of cache/ (shader
# list, build metadata) is harmless and stays on disk.
SKIP_TOP_DIRS = {"saves"}
CACHE_TOP_DIR = "cache"
SENSITIVE_CACHE_EXTS = (".rpyb",)  # script-derived compiled/analysis caches
SKIP_FILES = {CONTAINER_NAME, EXTENSION_NAME}

# Files read OUTSIDE renpy.loader (by the Steam SDK or the native launcher), so
# they must stay as plaintext on disk. Kept unencrypted by default; add more via
# the `keep_on_disk` config key. See docs/m4.md.
DEFAULT_KEEP_ON_DISK = ["steam_appid.txt"]

SUPPORTED_STRENGTHS = {"baseline"}

# Highest plugin-interface version this tool speaks (see docs/interface.md).
PLUGIN_INTERFACE = 1

# The closed poly plugin is a single prebuilt binary, distributed from the PUBLIC
# RenMori release (free to use; only the source is closed). When no plugin is
# supplied, the CLI downloads the right one for this platform, verifies it against
# the release's SHA256SUMS, and caches it. All of this is overridable by env for
# air-gapped builds and for pointing at a staging release:
#   RENMORI_PLUGIN            explicit plugin path (skips everything below)
#   RENMORI_NO_DOWNLOAD=1     never auto-download (fail/fall back instead)
#   RENMORI_PLUGIN_BASE_URL   where <asset> and SHA256SUMS live (default: the release)
#   RENMORI_PLUGIN_TAG        release tag to pull (default: PLUGIN_RELEASE_TAG)
PLUGIN_RELEASE_TAG = "plugin-v1.2.5"
PLUGIN_RELEASE_BASE = "https://github.com/MewBaka/RenMori/releases/download"
_PLUGIN_ASSET = {
    "linux": "renmori-plugin-linux-x64",
    "win32": "renmori-plugin-win-x64.exe",
}

EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_USAGE = 2


# --- i18n ------------------------------------------------------------------
#
# Only human-facing stderr text is localized. JSON on stdout, its field names,
# exit codes, and the technical `message`/`problems` strings stay English so CI
# scripts parse the same output in any locale. English is the fallback.

_LANG = "en"

_MESSAGES = {
    "about_to_protect": {"en": "About to protect", "zh": "即将保护"},
    "strength":         {"en": "Strength", "zh": "强度"},
    "auto":             {"en": "auto", "zh": "自动"},
    "input":            {"en": "Input",    "zh": "输入"},
    "mode":             {"en": "Mode",     "zh": "模式"},
    "files":            {"en": "Files",    "zh": "文件"},
    "scripts":          {"en": "Scripts",  "zh": "脚本"},
    "lockdown":         {"en": "Lockdown", "zh": "锁定"},
    "keys":             {"en": "Keys",     "zh": "密钥"},
    "output":           {"en": "Output",   "zh": "输出"},
    "backup":           {"en": "Backup",   "zh": "备份"},
    "container":        {"en": "Container", "zh": "容器"},
    "mode_copy":        {"en": "copy to {out}", "zh": "复制到 {out}"},
    "mode_inplace":     {"en": "in place (original -> {bak})",
                         "zh": "就地保护(原件 -> {bak})"},
    "mode_inplace_nobak": {"en": "in place, NO backup", "zh": "就地保护,不备份"},
    "files_val":        {"en": "{n} to encrypt, {k} kept on disk",
                         "zh": "{n} 个将加密,{k} 个保留明文"},
    "scripts_val":      {"en": "{n} .rpyc to transform", "zh": "{n} 个 .rpyc 将变换"},
    "lockdown_on":      {"en": "on (console/developer/export disabled)",
                         "zh": "开启(禁用控制台/开发者/导出)"},
    "lockdown_off":     {"en": "off", "zh": "关闭"},
    "key_random":       {"en": "random", "zh": "随机"},
    "warn_delete":      {"en": "In-place protection deletes the plaintext originals under game/.",
                         "zh": "就地保护会删除 game/ 下的明文原件。"},
    "warn_backup":      {"en": "A backup will be written to {bak} first.",
                         "zh": "将先备份到 {bak},可随时还原。"},
    "warn_nobak":       {"en": "No backup will be made (--no-backup). This cannot be undone.",
                         "zh": "不会创建备份(--no-backup),此操作无法撤销。"},
    "warn_from_zip":    {"en": "The source .zip is kept untouched as your original.",
                         "zh": "源 .zip 保持不变,可作为原件。"},
    "proceed":          {"en": "Proceed? [y/N] ", "zh": "继续? [y/N] "},
    "aborted":          {"en": "Aborted.", "zh": "已取消。"},
    "using_config":     {"en": "using config {path}", "zh": "使用配置 {path}"},
    "key_note":         {"en": "{var} not set; using a random key",
                         "zh": "{var} 未设置,改用随机密钥"},
    "step_backup":      {"en": "Backed up original -> {bak}", "zh": "已备份原件 -> {bak}"},
    "step_copy":        {"en": "Copied -> {out}", "zh": "已复制到 -> {out}"},
    "step_pack":        {"en": "Packed {n} files ({size}) -> {name}",
                         "zh": "已打包 {n} 个文件({size})-> {name}"},
    "step_scripts":     {"en": "Transformed {n} scripts", "zh": "已变换 {n} 个脚本"},
    "step_stripped":    {"en": "Stripped {n} source file(s) (.rpy); the engine runs the .rpyc",
                         "zh": "已剥离 {n} 个源码文件(.rpy);引擎用 .rpyc 运行"},
    "step_remove":      {"en": "Removed plaintext originals", "zh": "已删除明文原件"},
    "step_ext":         {"en": "Wrote loader extension {name}", "zh": "已写入加载扩展 {name}"},
    "step_manifest":    {"en": "Wrote {name}", "zh": "已写入 {name}"},
    "protected":        {"en": "Protected", "zh": "保护完成"},
    "files_done":       {"en": "{n} protected, {s} scripts", "zh": "{n} 个已保护,{s} 个脚本"},
    "next_release":     {"en": "Next - package & publish (this folder is the release):",
                         "zh": "下一步 —— 打包并发布(这个文件夹就是发行版):"},
    "hint_verify":      {"en": "Verify the build", "zh": "校验这个构建"},
    "hint_zip":         {"en": "Zip the folder for itch.io / direct download",
                         "zh": "压缩整个文件夹用于 itch.io / 直接下载"},
    "hint_steam":       {"en": "For Steam: upload this folder's contents via SteamPipe (not a .zip)",
                         "zh": "发布到 Steam:用 SteamPipe 上传这个文件夹的内容(不是 .zip)"},
    "hint_steam_doc":   {"en": "walkthrough: docs/steam-release.md",
                         "zh": "走查文档:docs/steam-release.md"},
    "hint_ship":        {"en": "Ship renmori.rmc and renmori.rpe together; keep _bak and keys out.",
                         "zh": "renmori.rmc 与 renmori.rpe 一起发;_bak 与密钥不要进包。"},
    "hint_norebuild":   {"en": "Don't re-run the Ren'Py launcher on this folder - it rebuilds "
                               "from source and drops the protection.",
                         "zh": "不要再对这个文件夹跑 Ren'Py 启动器构建——它会从源码重建并丢掉保护。"},
    "done":             {"en": "Done in {t}s", "zh": "用时 {t}s"},
    "unzipped":         {"en": "Unzipped {name} -> {out}", "zh": "已解压 {name} -> {out}"},
    "plugin_prompt":    {"en": "Full protection needs the closed plugin. Download {asset} from\n     {url} ? [Y/n] ",
                         "zh": "完整保护需要闭源插件。从下面下载 {asset}?\n     {url} [Y/n] "},
    "plugin_downloading": {"en": "Downloading {asset}", "zh": "正在下载 {asset}"},
    "plugin_cached":    {"en": "Plugin ready: {path}", "zh": "插件就绪:{path}"},
    "plugin_using_cached": {"en": "Using cached plugin {path}", "zh": "使用已缓存插件 {path}"},
    "plugin_declined":  {"en": "Download declined; no plugin available",
                         "zh": "已拒绝下载,无可用插件"},
    "plugin_dl_fail":   {"en": "Could not download the plugin: {err}",
                         "zh": "插件下载失败:{err}"},
    "plugin_verify_fail": {"en": "Downloaded plugin failed its checksum; discarded",
                           "zh": "下载的插件校验不通过,已丢弃"},
    "verifying":        {"en": "Verifying {dir}", "zh": "校验 {dir}"},
    "verified":         {"en": "Verified", "zh": "校验通过"},
    "problems_found":   {"en": "Problems found:", "zh": "发现问题:"},
}


def _t(key, **kw):
    s = _MESSAGES[key][_LANG]
    return s.format(**kw) if kw else s


def _detect_lang():
    """Resolve 'en'/'zh' from RENMORI_LANG, the locale env vars, or the OS."""
    v = os.environ.get("RENMORI_LANG")
    if not v:
        for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
            if os.environ.get(var):
                v = os.environ[var]
                break
    if not v:
        try:
            import locale
            v = locale.getlocale()[0] or ""
        except Exception:  # noqa: BLE001
            v = ""
    if not v and sys.platform == "win32":
        try:
            import ctypes
            # Low 10 bits are the primary language; 0x04 == Chinese.
            if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3ff) == 0x04:
                v = "zh"
        except Exception:  # noqa: BLE001
            pass
    return "zh" if (v or "en").lower().startswith("zh") else "en"


# --- styling ---------------------------------------------------------------
#
# Pure ANSI, no dependency. Enabled only on a real terminal (and honoring
# NO_COLOR / --no-color). Width maths are CJK-aware so panels align in any
# language. All of this writes to stderr via _log; stdout stays JSON-only.

_QUIET = False
_COLOR = False
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _c(code, s):
    return "\x1b[%sm%s\x1b[0m" % (code, s) if _COLOR else s


def _bold(s):   return _c("1", s)
def _dim(s):    return _c("2", s)
def _red(s):    return _c("31", s)
def _green(s):  return _c("32", s)
def _yellow(s): return _c("33", s)
def _cyan(s):   return _c("36", s)


def _dw(s):
    """Display width, ignoring ANSI, counting CJK/full-width chars as 2."""
    s = _ANSI_RE.sub("", s)
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _fit(s, width):
    pad = width - _dw(s)
    return s + " " * pad if pad > 0 else s


def _human(n):
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return "%d %s" % (int(size), unit) if unit == "B" else "%.1f %s" % (size, unit)
        size /= 1024.0


def _log(msg=""):
    if not _QUIET:
        print(msg, file=sys.stderr)


def _note(msg):
    _log("  " + _dim(msg))


def _step(msg, ok=True):
    _log("  %s %s" % (_green("✓") if ok else _red("✗"), msg))


def _banner():
    _log()
    _log("  %s %s · %s" % (_bold(_cyan(BRAND)), __version__, "baseline"))
    _log()


def _panel(title, items, tint=_cyan):
    """Render a titled box of (label, value) rows. Returns a multi-line string."""
    labels = [str(l) for l, _ in items]
    lw = max((_dw(l) for l in labels), default=0)
    body = [_fit(str(l), lw) + "   " + str(v) for l, v in items]
    inner = max([_dw(b) for b in body] + [_dw(title) + 1])
    dashes = inner - _dw(title) - 1
    out = ["  " + tint("┌─ ") + _bold(title) + tint(" " + "─" * dashes + "┐")]
    for b in body:
        out.append("  " + tint("│ ") + b + " " * (inner - _dw(b)) + tint(" │"))
    out.append("  " + tint("└" + "─" * (inner + 2) + "┘"))
    return "\n".join(out)


def _fail(msg, code=EXIT_USAGE):
    print(("  " + _red("✗ ") + msg) if not _QUIET else ("error: " + msg), file=sys.stderr)
    print(json.dumps({"status": "error", "message": msg}))
    return code


def _confirm(args):
    """True to proceed. Auto-yes when non-interactive, --quiet, or -y, so CI never blocks."""
    if getattr(args, "yes", False) or _QUIET or not sys.stdin.isatty():
        return True
    sys.stderr.write("  " + _yellow("? ") + _t("proceed"))
    sys.stderr.flush()
    try:
        ans = input()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans.strip().lower() in ("y", "yes")


# --- argument parsing ------------------------------------------------------

def cmd_gui(args):
    """Launch the Tkinter front-end (imported lazily so the CLI never needs it)."""
    from . import gui
    return gui.run(lang=_LANG)


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--lang", choices=("auto", "en", "zh"), default="auto",
                        help="output language (default: follow the system locale)")
    common.add_argument("--no-color", action="store_true", help="disable colored output")
    common.add_argument("--quiet", action="store_true", help="only emit the final JSON result")

    parser = argparse.ArgumentParser(
        prog="renmori",
        description="Protect a built Ren'Py game.",
        epilog="Exit codes: 0 success, 2 usage/precondition error, 1 runtime failure.",
    )
    parser.add_argument("--version", action="version", version="%s %s" % (BRAND, __version__))
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("protect", parents=[common], help="protect a built Ren'Py game directory")
    p.add_argument("game_dir", help="built game directory (contains 'game/'), or a .zip of one")
    p.add_argument("-o", "--output", help="output directory (default: protect in place)")
    p.add_argument("-c", "--config", help="path to renmori.toml (default: autodetect)")
    p.add_argument("--chunk-size", type=int, default=None, help="container chunk size in bytes")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="glob of game-relative paths to leave unencrypted (repeatable)")
    p.add_argument("--strength", default=None,
                   help="protection strength: default is full (the plugin's strongest, and fails "
                        "without a plugin); 'baseline' for the open format; 'auto' for full-else-baseline")
    p.add_argument("--plugin", default=None,
                   help="path to the closed protection plugin (else $RENMORI_PLUGIN)")
    p.add_argument("--platforms", default=None,
                   help="plugin only: comma list of target platforms (default: auto-detect)")
    p.add_argument("--launcher", action="store_true",
                   help="plugin only: bind keys to a native launcher and ship it")
    p.add_argument("--no-lockdown", dest="lockdown", action="store_false", default=None,
                   help="do not disable console/developer/export in the build")
    p.add_argument("--keep-plaintext", action="store_true", help="don't delete packed originals (debug)")
    p.add_argument("--no-backup", action="store_true",
                   help="protect in place WITHOUT first copying the original to <dir>_bak "
                        "(no effect with -o, which already protects a copy)")
    p.add_argument("--no-hints", action="store_true",
                   help="don't print the 'package & publish' guidance on success")
    p.add_argument("-y", "--yes", action="store_true",
                   help="skip the pre-protect confirmation prompt")
    p.set_defaults(func=cmd_protect)

    v = sub.add_parser("verify", parents=[common], help="check a protected build against its manifest")
    v.add_argument("protected_dir", help="a directory produced by 'renmori protect'")
    v.set_defaults(func=cmd_verify)

    sub.add_parser("gui", parents=[common],
                   help="launch the graphical interface (Tkinter)").set_defaults(func=cmd_gui)

    args = parser.parse_args(argv)

    global _QUIET, _COLOR, _LANG
    _QUIET = args.quiet
    _LANG = _detect_lang() if args.lang == "auto" else args.lang
    _COLOR = (not args.no_color and os.environ.get("NO_COLOR") is None
              and sys.stderr.isatty())
    return args.func(args)


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
        _note(_t("using_config", path=cfg_path))

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
        # None means "auto": the strongest the plugin offers, else baseline.
        "strength": args.strength or file_cfg.get("strength") or None,
        "lockdown": args.lockdown if args.lockdown is not None else file_cfg.get("lockdown", True),
        "keep_plaintext": args.keep_plaintext or file_cfg.get("keep_plaintext", False),
        "master_env": keys.get("master_env"),
        "script_env": keys.get("script_env"),
        "platforms": (
            [p.strip() for p in args.platforms.split(",") if p.strip()] if args.platforms
            else file_cfg.get("platforms") or None),
        "launcher": bool(getattr(args, "launcher", False)) or bool(file_cfg.get("launcher", False)),
    }
    return settings


def _key_from_env(var):
    """Return a 32-byte key from a hex env var, or a fresh random key if unset."""
    if not var:
        return os.urandom(32), "random"
    raw = os.environ.get(var)
    if not raw:
        _note(_t("key_note", var=var))
        return os.urandom(32), "random"
    try:
        key = bytes.fromhex(raw.strip())
    except ValueError:
        raise RuntimeError("%s must be hex" % var)
    if len(key) != 32:
        raise RuntimeError("%s must be 32 bytes (64 hex chars), got %d" % (var, len(key)))
    return key, "env:" + var


def _key_label(src):
    return _t("key_random") if src == "random" else src


# --- protect ---------------------------------------------------------------

def _safe_extract(z, dest):
    """Extract a zip, refusing any member that would escape `dest` (zip-slip) and
    restoring each entry's stored Unix permissions. `ZipFile.extractall` drops the
    executable bit, which would leave the mac `.app` launcher (Contents/MacOS/*)
    and the `.sh` launcher non-executable, so the distribution can no longer be
    started ("the application can't be opened")."""
    dest = pathlib.Path(dest).resolve()
    for info in z.infolist():
        target = (dest / info.filename).resolve()
        if target != dest and not str(target).startswith(str(dest) + os.sep):
            raise RuntimeError("unsafe path in archive: %s" % info.filename)
        z.extract(info, str(dest))
        mode = (info.external_attr >> 16) & 0o7777
        if mode and not info.is_dir():
            os.chmod(target, mode)


def _find_build_root(root):
    """Find the Ren'Py build directory (the one holding 'game/') in an extracted
    archive: the root itself, or a single top-level subfolder (dists usually wrap
    the build in one). Ambiguity or absence is an error the caller reports."""
    root = pathlib.Path(root)
    if (root / "game").is_dir():
        return root
    cands = [d for d in sorted(root.iterdir()) if d.is_dir() and (d / "game").is_dir()]
    if len(cands) == 1:
        return cands[0]
    if not cands:
        raise RuntimeError("no 'game/' directory found in the archive")
    raise RuntimeError("the archive holds more than one game build (%s); unzip it and "
                       "point renmori at the one you want" % ", ".join(d.name for d in cands))


def _stage_zip(args):
    """If game_dir is a .zip, extract it, locate the build root inside, and move it
    to the output directory, then rewrite args to protect that folder in place —
    the .zip stays as the pristine original, so no backup is made. With no -o the
    output defaults to a sibling folder named after the archive. Returns the
    staging temp dir to clean up, or None when the input was not a zip."""
    p = pathlib.Path(args.game_dir)
    if not p.is_file() or not zipfile.is_zipfile(str(p)):
        return None

    out_root = pathlib.Path(args.output).resolve() if args.output else (p.parent / p.stem).resolve()
    if out_root.exists():
        raise RuntimeError("output %s already exists" % out_root)
    out_root.parent.mkdir(parents=True, exist_ok=True)

    staging = pathlib.Path(tempfile.mkdtemp(prefix=".renmori-unzip-", dir=str(out_root.parent)))
    try:
        with zipfile.ZipFile(str(p)) as z:
            _safe_extract(z, staging)
        build_root = _find_build_root(staging)
        shutil.move(str(build_root), str(out_root))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if out_root.exists():
            shutil.rmtree(out_root, ignore_errors=True)
        raise

    _note(_t("unzipped", name=p.name, out=out_root))
    args.game_dir = str(out_root)
    args.output = None
    args.no_backup = True
    args._from_zip = True
    return staging


def cmd_protect(args):
    started = time.monotonic()
    _banner()
    staging = None
    try:
        staging = _stage_zip(args)
    except (RuntimeError, OSError, zipfile.BadZipFile) as e:
        return _fail(str(e))
    try:
        return _do_protect(args, started)
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def _do_protect(args, started):
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

    # Settle the strength and, when full protection is wanted, obtain the closed
    # plugin: explicit --plugin/$RENMORI_PLUGIN, else a cached download, else fetch
    # it from the public release (prompted on a terminal, automatic in CI). The
    # default is FULL protection; with no plugin it fails rather than silently
    # shipping the weak baseline. Baseline is a deliberate opt-in that never
    # triggers a download; `auto` keeps the graceful full-else-baseline fallback.
    requested = settings["strength"]  # None unless the user set it
    plugin_path = caps = None
    plugin_strengths = []
    if requested != "baseline":
        plugin_path = _ensure_plugin(args)
        caps = _query_capabilities(plugin_path) if plugin_path else None
        plugin_strengths = caps.get("strengths", []) if caps else []

    if requested == "auto":
        strength = plugin_strengths[0] if plugin_strengths else "baseline"
    elif requested is None:
        if not plugin_strengths:
            return _fail("full protection needs the closed plugin; set RENMORI_PLUGIN or "
                         "--plugin, or pass --strength baseline for the open baseline format")
        strength = plugin_strengths[0]
    else:
        strength = requested
    settings["strength"] = strength

    if strength != "baseline":
        if strength not in plugin_strengths:
            return _fail("strength %r requires the closed renmori plugin; set RENMORI_PLUGIN "
                         "or pass --plugin (or use --strength baseline)" % strength)
        return _protect_with_plugin(args, plugin_path, caps, src_root, settings, started)

    try:
        master_key, master_src = _key_from_env(settings["master_env"])
        script_key, script_src = _key_from_env(settings["script_env"])
    except RuntimeError as e:
        return _fail(str(e))

    # Resolve the output/backup target and fail fast on collisions, before any
    # heavy work or the confirmation prompt.
    backup_root = None
    if args.output:
        out_root = pathlib.Path(args.output).resolve()
        if out_root.exists():
            return _fail("output %s already exists" % out_root)
    else:
        out_root = src_root
        if not args.no_backup:
            backup_root = src_root.parent / (src_root.name + "_bak")
            if backup_root.exists():
                return _fail("backup %s already exists; remove it, pass --no-backup to "
                             "overwrite in place, or use -o to protect a copy" % backup_root)

    # Walk the source to show counts (the copy, if any, is identical).
    to_pack, excluded = _partition(game_dir, settings["exclude"])
    to_pack, _dropped = _strip_source(to_pack)
    if not to_pack:
        return _fail("nothing to pack under %s" % game_dir)
    script_total = sum(1 for _, rel in to_pack if rel.lower().endswith(SCRIPT_EXTENSIONS))

    # Pre-flight summary.
    if args.output:
        mode = _t("mode_copy", out=out_root)
    elif backup_root is not None:
        mode = _t("mode_inplace", bak=backup_root)
    else:
        mode = _t("mode_inplace_nobak")
    _log(_panel(_t("about_to_protect"), [
        (_t("input"), src_root),
        (_t("mode"), mode),
        (_t("files"), _t("files_val", n=len(to_pack), k=len(excluded))),
        (_t("scripts"), _t("scripts_val", n=script_total)),
        (_t("lockdown"), _t("lockdown_on") if settings["lockdown"] else _t("lockdown_off")),
        (_t("keys"), "master=%s · script=%s" % (_key_label(master_src), _key_label(script_src))),
    ]))
    _log()

    # Destructive-action notice (in-place only) + confirmation.
    if not args.output:
        _log("  " + _yellow("⚠  ") + _t("warn_delete"))
        if backup_root:
            _log("     " + _t("warn_backup", bak=backup_root))
        elif getattr(args, "_from_zip", False):
            _log("     " + _t("warn_from_zip"))
        else:
            _log("     " + _t("warn_nobak"))
        _log()
    if not _confirm(args):
        _log("  " + _t("aborted"))
        print(json.dumps({"status": "aborted"}))
        return EXIT_USAGE

    # Now do the real work.
    if args.output:
        shutil.copytree(src_root, out_root)
        _step(_t("step_copy", out=out_root))
    elif backup_root is not None:
        shutil.copytree(src_root, backup_root)
        _step(_t("step_backup", bak=backup_root))

    out_game = out_root / "game"
    to_pack, excluded = _partition(out_game, settings["exclude"])
    to_pack, dropped_src = _strip_source(to_pack)

    container_path = out_game / CONTAINER_NAME
    manifest_files = []
    script_count = 0

    # A .rpa archive is unpacked and its entries packed as individual files, so
    # the engine can still find the scripts and assets once the archive is gone.
    seen = set()

    def _pack(w, name, data=None, src=None):
        nonlocal script_count
        name = normalize_name(name)
        if name in seen:
            return  # a loose file duplicated by an archive entry: first wins
        seen.add(name)
        if name.lower().endswith(SCRIPT_EXTENSIONS):
            raw = data if data is not None else pathlib.Path(src).read_bytes()
            w.add_bytes(name, transform_rpyc(raw, script_key))
            script_count += 1
            size = len(raw)
        elif data is not None:
            w.add_bytes(name, data)
            size = len(data)
        else:
            w.add_file(name, src)
            size = os.path.getsize(src)
        manifest_files.append({"name": name, "size": size})

    try:
        with ContainerWriter(str(container_path), master_key, chunk_size=settings["chunk_size"]) as w:
            for abs_path, rel_name in to_pack:
                if rel_name.lower().endswith(".rpa"):
                    for inner, data in read_rpa(str(abs_path)):
                        _pack(w, inner, data=data)
                else:
                    _pack(w, rel_name, src=str(abs_path))
    except Exception as e:  # noqa: BLE001
        return _fail("packing failed: %s" % e, EXIT_RUNTIME)

    container_bytes = container_path.stat().st_size
    _step(_t("step_pack", n=len(manifest_files), size=_human(container_bytes), name=CONTAINER_NAME))
    _step(_t("step_scripts", n=script_count))

    if dropped_src:
        _step(_t("step_stripped", n=len(dropped_src)))
    if not settings["keep_plaintext"]:
        # Delete both the packed originals and the stripped source.
        _remove_packed(out_game, to_pack + dropped_src)
        _step(_t("step_remove"))

    _write_extension(out_game / EXTENSION_NAME, master_key, script_key, settings["lockdown"])
    _step(_t("step_ext", name=EXTENSION_NAME))
    manifest = _write_manifest(out_root, container_path, manifest_files, settings)
    _step(_t("step_manifest", name=MANIFEST_NAME))

    # Result panel.
    rows = [(_t("output"), out_root)]
    if backup_root is not None:
        rows.append((_t("backup"), backup_root))
    rows.append((_t("container"), "%s · sha256 %s…" % (_human(container_bytes),
                                                        manifest["container_sha256"][:12])))
    rows.append((_t("files"), _t("files_done", n=len(manifest_files), s=script_count)))
    _log()
    _log(_panel(_t("protected"), rows, tint=_green))
    _log()

    if not args.no_hints:
        _release_hints(out_root)

    _log("  " + _green("✓ ") + _t("done", t="%.1f" % (time.monotonic() - started)))

    result = {"status": "ok", "output": str(out_root), "manifest": manifest}
    if backup_root is not None:
        result["backup"] = str(backup_root)
    print(json.dumps(result))
    return EXIT_OK


def _release_hints(out_root):
    parent = out_root.parent
    name = out_root.name
    _log("  " + _bold(_t("next_release")))
    _log()
    _log("    1. " + _t("hint_verify"))
    _log("       " + _dim("renmori verify %s" % out_root))
    _log()
    _log("    2. " + _t("hint_zip"))
    _log("       " + _dim("cd %s && zip -r %s.zip %s" % (parent, name, name)))
    _log()
    _log("    3. " + _t("hint_steam"))
    _log("       " + _dim(_t("hint_steam_doc")))
    _log()
    _log("    4. " + _t("hint_ship"))
    _log("       " + _yellow(_t("hint_norebuild")))
    _log()


# --- closed-plugin integration (see docs/interface.md) --------------------

def _plugin_asset():
    """The release asset name for this platform, or None if unsupported. macOS
    ships a binary per arch (arm64 / Intel x86_64); the others are single-arch."""
    if sys.platform == "darwin":
        import platform
        return "renmori-plugin-mac-" + ("arm64" if platform.machine() == "arm64" else "x86_64")
    return _PLUGIN_ASSET.get("linux" if sys.platform.startswith("linux") else sys.platform)


def _plugin_cache_dir():
    tag = os.environ.get("RENMORI_PLUGIN_TAG", PLUGIN_RELEASE_TAG)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "renmori", "plugin", tag)


def _find_plugin(args):
    """Explicit plugin only: --plugin / $RENMORI_PLUGIN. No cache, no download."""
    path = args.plugin or os.environ.get("RENMORI_PLUGIN")
    if not path:
        return None
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(path):
        _note("plugin not found, ignoring: %s" % path)
        return None
    return path


def _ensure_plugin(args):
    """Resolve the closed plugin: explicit path, else a cached download, else fetch
    it from the public release. Returns a path, or None when none is available
    (no asset for this platform, download disabled or declined, or a fetch error).
    The caller turns None into the clear 'needs the closed plugin' failure."""
    explicit = _find_plugin(args)
    if explicit:
        return explicit

    asset = _plugin_asset()
    if not asset:
        return None  # unknown platform; nothing to fetch

    cached = os.path.join(_plugin_cache_dir(), asset)
    if os.path.exists(cached):
        _note(_t("plugin_using_cached", path=cached))
        return cached

    if os.environ.get("RENMORI_NO_DOWNLOAD"):
        return None
    return _download_plugin(args, asset, cached)


def _download_plugin(args, asset, dest):
    """Fetch `asset` from the release, verify its SHA256SUMS line, cache it at
    `dest`, and return the path (None on decline/error). Prompts on an interactive
    terminal; downloads without asking in CI, --quiet, or with -y."""
    tag = os.environ.get("RENMORI_PLUGIN_TAG", PLUGIN_RELEASE_TAG)
    base = os.environ.get("RENMORI_PLUGIN_BASE_URL") or (PLUGIN_RELEASE_BASE + "/" + tag)
    base = base.rstrip("/")
    url = base + "/" + asset

    # Confirm, unless non-interactive / -y / --quiet (CI downloads silently).
    interactive = sys.stdin.isatty() and not _QUIET and not getattr(args, "yes", False)
    if interactive:
        sys.stderr.write("  " + _yellow("? ") + _t("plugin_prompt", asset=asset, url=url))
        sys.stderr.flush()
        try:
            ans = input()
        except (EOFError, KeyboardInterrupt):
            ans = "n"
        if ans.strip().lower() in ("n", "no"):
            _note(_t("plugin_declined"))
            return None

    try:
        sums = urllib.request.urlopen(base + "/SHA256SUMS", timeout=60).read().decode("utf-8")
        want = _sha_for(sums, asset)
        if not want:
            raise RuntimeError("no SHA256SUMS entry for %s" % asset)
        _step(_t("plugin_downloading", asset=asset))
        blob = urllib.request.urlopen(url, timeout=600).read()
    except Exception as e:  # noqa: BLE001 - any fetch error -> no plugin, clear message
        _note(_t("plugin_dl_fail", err=e))
        return None

    if hashlib.sha256(blob).hexdigest() != want:
        _note(_t("plugin_verify_fail"))
        return None

    # Write atomically into the cache, and make it executable.
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part." + os.urandom(4).hex()
    with open(tmp, "wb") as f:
        f.write(blob)
    if sys.platform != "win32":
        os.chmod(tmp, 0o755)
    os.replace(tmp, dest)
    _step(_t("plugin_cached", path=dest))
    return dest


def _sha_for(sums_text, asset):
    """Pull the hex digest for `asset` out of a `sha256  name` SHA256SUMS file."""
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and os.path.basename(parts[1]) == asset:
            return parts[0].lower()
    return None


def _plugin_base_cmd(plugin_path):
    # A .py plugin runs under this interpreter; anything else runs directly.
    if plugin_path.endswith(".py"):
        return [sys.executable, plugin_path]
    return [plugin_path]


def _query_capabilities(plugin_path):
    try:
        proc = subprocess.run(_plugin_base_cmd(plugin_path) + ["capabilities"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, timeout=30)
        if proc.returncode != 0:
            return None
        caps = json.loads(proc.stdout)
    except Exception:  # noqa: BLE001 - a broken plugin is treated as absent
        return None
    if not isinstance(caps.get("interface"), int) or caps["interface"] < PLUGIN_INTERFACE:
        _note("plugin interface %r unsupported (need %d); ignoring it"
              % (caps.get("interface"), PLUGIN_INTERFACE))
        return None
    return caps


def _run_plugin_protect(plugin_path, request):
    # stdout carries the JSON response; the plugin's progress streams to stderr.
    proc = subprocess.run(_plugin_base_cmd(plugin_path) + ["protect"],
                          input=json.dumps(request), text=True, stdout=subprocess.PIPE)
    resp = None
    if proc.stdout and proc.stdout.strip():
        try:
            resp = json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            resp = None
    return proc.returncode, resp


def _protect_with_plugin(args, plugin_path, caps, src_root, settings, started):
    game_dir = src_root / "game"
    to_pack, excluded = _partition(game_dir, settings["exclude"])
    if not to_pack:
        return _fail("nothing to pack under %s" % game_dir)
    script_total = sum(1 for _, rel in to_pack if rel.lower().endswith(SCRIPT_EXTENSIONS))

    # The plugin always reads `source` and writes a fresh `out_root`. In-place is
    # "move the original aside, then protect into its old path".
    backup_root = None
    restore = None  # (moved_to, original) to undo if the plugin fails
    if args.output:
        out_root = pathlib.Path(args.output).resolve()
        if out_root.exists():
            return _fail("output %s already exists" % out_root)
        source = src_root
        mode = _t("mode_copy", out=out_root)
    else:
        out_root = src_root
        if not args.no_backup:
            backup_root = src_root.parent / (src_root.name + "_bak")
            if backup_root.exists():
                return _fail("backup %s already exists; remove it, pass --no-backup, or use -o"
                             % backup_root)
            source = backup_root
            mode = _t("mode_inplace", bak=backup_root)
        else:
            source = src_root.parent / ("." + src_root.name + ".renmori-src." + os.urandom(4).hex())
            mode = _t("mode_inplace_nobak")

    platforms_label = ",".join(settings["platforms"]) if settings["platforms"] else _t("auto")
    _log(_panel(_t("about_to_protect"), [
        (_t("input"), src_root),
        (_t("mode"), mode),
        (_t("strength"), "%s · %s %s" % (settings["strength"], caps.get("name", "plugin"),
                                         caps.get("version", ""))),
        (_t("files"), _t("files_val", n=len(to_pack), k=len(excluded))),
        (_t("scripts"), _t("scripts_val", n=script_total)),
        ("Platforms", platforms_label),
        (_t("lockdown"), _t("lockdown_on") if settings["lockdown"] else _t("lockdown_off")),
    ]))
    _log()
    if not args.output:
        _log("  " + _yellow("⚠  ") + _t("warn_delete"))
        if backup_root:
            _log("     " + _t("warn_backup", bak=backup_root))
        elif getattr(args, "_from_zip", False):
            _log("     " + _t("warn_from_zip"))
        else:
            _log("     " + _t("warn_nobak"))
        _log()
    if not _confirm(args):
        _log("  " + _t("aborted"))
        print(json.dumps({"status": "aborted"}))
        return EXIT_USAGE

    # Move the original aside for in-place, so the plugin writes a fresh tree.
    if out_root == src_root:
        shutil.move(str(src_root), str(source))
        restore = (source, src_root)

    request = {
        "interface": PLUGIN_INTERFACE,
        "source_dir": str(source),
        "output_dir": str(out_root),
        "strength": settings["strength"],
        "platforms": settings["platforms"],
        "launcher": bool(settings["launcher"]),
        "exclude": settings["exclude"],
        "chunk_size": settings["chunk_size"],
        "lockdown": bool(settings["lockdown"]),
        "keys": {},
    }
    rc, resp = _run_plugin_protect(plugin_path, request)

    if rc != 0 or not isinstance(resp, dict) or resp.get("status") != "ok":
        # Restore the original and clean any partial output.
        if restore is not None:
            moved_to, original = restore
            if original.exists():
                shutil.rmtree(original, ignore_errors=True)
            if moved_to.exists():
                shutil.move(str(moved_to), str(original))
        elif args.output and out_root.exists():
            shutil.rmtree(out_root, ignore_errors=True)
        msg = resp.get("message") if isinstance(resp, dict) else None
        return _fail("plugin protection failed" + (": " + msg if msg else ""), EXIT_RUNTIME)

    # In-place no-backup: the temporary original copy was consumed; drop it.
    if restore is not None and backup_root is None:
        shutil.rmtree(restore[0], ignore_errors=True)

    manifest = _write_plugin_manifest(out_root, resp, settings)
    _step(_t("step_pack", n=resp.get("files", 0),
             size="sha256 %s…" % (resp.get("container_sha256") or "")[:12],
             name=resp.get("container", CONTAINER_NAME)))
    _step(_t("step_scripts", n=resp.get("scripts", 0)))

    rows = [(_t("output"), out_root)]
    if backup_root is not None:
        rows.append((_t("backup"), backup_root))
    rows.append((_t("strength"), settings["strength"]))
    rows.append((_t("container"), "sha256 %s…" % (resp.get("container_sha256") or "")[:12]))
    rows.append((_t("files"), _t("files_done", n=resp.get("files", 0), s=resp.get("scripts", 0))))
    _log()
    _log(_panel(_t("protected"), rows, tint=_green))
    _log()
    if not args.no_hints:
        _release_hints(out_root)
    _log("  " + _green("✓ ") + _t("done", t="%.1f" % (time.monotonic() - started)))

    result = {"status": "ok", "output": str(out_root), "manifest": manifest}
    if backup_root is not None:
        result["backup"] = str(backup_root)
    print(json.dumps(result))
    return EXIT_OK


def _write_plugin_manifest(out_root, resp, settings):
    manifest = {
        "renmori_version": __version__,
        "container_format": "poly",
        "strength": resp.get("strength", settings["strength"]),
        "lockdown": bool(settings["lockdown"]),
        "container": resp.get("container"),
        "container_sha256": resp.get("container_sha256"),
        "file_count": resp.get("files", 0),
        "script_count": resp.get("scripts", 0),
        "platforms": resp.get("platforms", []),
        "cores": resp.get("cores", []),
        "launcher": resp.get("launcher"),
    }
    (out_root / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"file_count": resp.get("files", 0),
            "container_sha256": resp.get("container_sha256"),
            "strength": resp.get("strength", settings["strength"])}


def _excluded(rel_name, patterns):
    return any(fnmatch.fnmatch(rel_name, pat) for pat in patterns)


def read_rpa(path):
    """Yield (game-relative name, bytes) for each entry in a Ren'Py RPA archive
    (RPA-3.0 or 2.0). A game built with the launcher ships its scripts and assets
    inside .rpa, so they are unpacked into the container as individual files;
    otherwise the engine cannot find them once the archive is encrypted. The
    archive is the developer's own build (trusted input)."""
    with open(path, "rb") as f:
        parts = f.readline().split()
        magic = parts[0]
        if magic == b"RPA-3.0":
            index_off, key = int(parts[1], 16), int(parts[2], 16)
        elif magic == b"RPA-2.0":
            index_off, key = int(parts[1], 16), 0
        else:
            raise RuntimeError("unsupported RPA archive format: %r"
                               % magic.decode("latin-1", "replace"))
        f.seek(index_off)
        index = pickle.loads(zlib.decompress(f.read()))
        for name, segments in index.items():
            buf = []
            for seg in segments:
                off, length = seg[0] ^ key, seg[1] ^ key
                prefix = seg[2] if len(seg) > 2 else b""
                if isinstance(prefix, str):
                    prefix = prefix.encode("latin-1")
                f.seek(off)
                buf.append(prefix + f.read(length))
            yield name, b"".join(buf)


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
            # Inside cache/, pack only the script-derived caches; leave the rest
            # (shaders.txt, build_info.json) untouched on disk.
            if top == CACHE_TOP_DIR and not fn.lower().endswith(SENSITIVE_CACHE_EXTS):
                continue
            abs_path = pathlib.Path(dirpath) / fn
            if abs_path.is_symlink() or not abs_path.is_file():
                continue
            rel_name = normalize_name(os.path.relpath(abs_path, game_dir))
            (excluded if _excluded(rel_name, excludes) else to_pack).append((abs_path, rel_name))
    return to_pack, excluded


def _strip_source(to_pack):
    """Split off Ren'Py source (.rpy/.rpym) that has a compiled sibling. Source is
    not needed at run time — the engine runs the .rpyc — and shipping it (even
    packed) would hand back pristine source on any decrypt, no decompilation
    needed. Source with no compiled form is kept so no content is lost.
    Returns (kept, dropped); dropped files are deleted, not packed."""
    names = {rel for _, rel in to_pack}
    kept, dropped = [], []
    for abs_path, rel in to_pack:
        low = rel.lower()
        compiled = (rel[:-4] + ".rpyc") if low.endswith(".rpy") else \
                   (rel[:-5] + ".rpymc") if low.endswith(".rpym") else None
        (dropped if (compiled and compiled in names) else kept).append((abs_path, rel))
    return kept, dropped


def _remove_packed(game_dir, to_pack):
    for abs_path, _ in to_pack:
        try:
            abs_path.unlink()
        except OSError as e:
            _note("warning: could not remove %s: %s" % (abs_path, e))
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

    _banner()
    _note(_t("verifying", dir=root))

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

    # No plaintext scripts, archives, or compiled-script caches should remain on
    # disk — including under cache/, which ships the scripts' bytecode.
    for p in game.rglob("*"):
        if p.suffix in (".rpa", ".rpyc", ".rpy", ".rpyb", ".rpymc") and p.is_file():
            problems.append("plaintext left: %s" % p.relative_to(root))
            break

    if problems:
        _log()
        _log("  " + _red(_t("problems_found")))
        for p in problems:
            _step(p, ok=False)
        _log()
        print(json.dumps({"status": "error", "problems": problems}))
        return EXIT_RUNTIME

    _log()
    _log(_panel(_t("verified"), [
        (_t("files"), manifest.get("file_count")),
        (_t("container"), "sha256 %s…" % str(manifest.get("container_sha256"))[:12]),
    ], tint=_green))
    _log()
    result = {"status": "ok", "file_count": manifest.get("file_count"),
              "container_sha256": manifest.get("container_sha256")}
    print(json.dumps(result))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
