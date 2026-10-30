# CLI usage

The `renmori` command-line tool protects a **built** Ren'Py 8.x (Python 3)
distribution. It makes no changes to your game's source — you run it on the
output of the Ren'Py launcher's *Build Distributions*.

- For CI pipelines and key management, see [ci.md](ci.md).
- For publishing to Steam, see [steam-release.md](steam-release.md).
- For the config file, see [`examples/renmori.toml`](../examples/renmori.toml).

---

## Install

Not on PyPI yet (version `0.0.1`). Install from source:

```bash
git clone <this-repo> renmori
cd renmori
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
renmori --version
```

Requires Python 3.9+ (reading a `renmori.toml` config needs 3.11+, or the
`tomli` package on older versions).

---

## Quick start

```bash
# 1. Build your game in the Ren'Py launcher (Build Distributions), then unzip it.
# 2. Protect the built folder into a new one:
renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected

# 3. Check it:
renmori verify ./dist/MyGame-1.0-pc-protected
```

The input is any directory that contains a `game/` subdirectory. `protect` packs
everything under `game/` into `game/renmori.rmc`, transforms the compiled
scripts, deletes the plaintext originals, writes the loader extension
`game/renmori.rpe`, and emits `renmori-manifest.json`.

---

## Commands

### `renmori protect <game-dir> [options]`

Protect a built game directory.

- **In place (default):** overwrites the directory, but first copies the
  original to a sibling `<dir>_bak`. On an interactive terminal it prints a
  summary and asks `[y/N]` before touching anything.
- **To a new directory:** `-o OUTPUT` protects a copy and leaves the original
  untouched (no backup is made in this mode).

### `renmori verify <protected-dir>`

Re-check a protected build against its `renmori-manifest.json`: container hash,
required files present, and no plaintext `.rpa`/`.rpyc`/`.rpy` left on disk. Use
it as a CI gate.

---

## Options (`protect`)

| Flag | Config key | Default | Notes |
|------|-----------|---------|-------|
| `-o, --output DIR` | — | in place | protect a copy in DIR (DIR must not exist); original untouched |
| `-c, --config FILE` | — | autodetect | else `<game-dir>/renmori.toml` or `./renmori.toml` |
| `--chunk-size N` | `chunk_size` | 65536 | container chunk size in bytes |
| `--exclude GLOB` | `exclude` | none | leave matching files unencrypted (repeatable; adds to config) |
| `--strength S` | `strength` | `baseline` | open tool: `baseline` only (see below) |
| `--no-lockdown` | `lockdown` | on | keep console/developer/export enabled |
| `--no-backup` | — | off | protect in place without the `<dir>_bak` copy (no effect with `-o`) |
| `--keep-plaintext` | `keep_plaintext` | off | don't delete packed originals (debug) |
| `-y, --yes` | — | off | skip the pre-protect confirmation prompt |
| `--no-hints` | — | off | don't print the "package & publish" guidance on success |

## Common options (both commands)

| Flag | Default | Notes |
|------|---------|-------|
| `--lang {auto,en,zh}` | `auto` | language of the human-facing output; `auto` follows the system locale. Also `RENMORI_LANG`. |
| `--no-color` | off | disable ANSI color. Color is auto-off when not a terminal, and honors `NO_COLOR`. |
| `--quiet` | off | suppress all styled stderr output; print only the final JSON line. |

---

## Output and exit codes

Human-facing progress (the banner, summary panel, step lines, result panel, and
release hints) goes to **stderr**, styled and localized. The **last line of
stdout is always a JSON object** with stable English keys:

```json
{"status": "ok", "output": "…", "manifest": {"file_count": 1994, "container_sha256": "…", "strength": "baseline"}, "backup": "…"}
```

so CI can parse the same output in any locale regardless of styling. `verify`
prints `{"status": "ok", "file_count": …, "container_sha256": "…"}` or
`{"status": "error", "problems": [...]}`.

| Code | Meaning |
|-----:|---------|
| 0 | success |
| 2 | usage / precondition (no `game/`, already protected, backup/output exists, aborted at the prompt, bad flags/config) |
| 1 | runtime failure (packing error, or `verify` mismatch) |

---

## Config file

Place a `renmori.toml` next to the game directory (or pass `-c`). Every field is
optional; CLI flags override it, and `--exclude` adds on top. Keys can be read
from environment variables for CI. Full reference:
[`examples/renmori.toml`](../examples/renmori.toml) and [ci.md](ci.md).

```toml
[protect]
chunk_size = 65536
exclude = ["thirdparty/*"]
lockdown = true

[keys]
# master_env = "RENMORI_MASTER_KEY"   # 64 hex chars; from your CI secret store
# script_env = "RENMORI_SCRIPT_KEY"
```

---

## Common workflows

**Protect a copy, keep the original:**

```bash
renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected
```

**Protect in place (keeps a `MyGame-1.0-pc_bak` backup):**

```bash
renmori protect ./dist/MyGame-1.0-pc
```

**Non-interactive / CI (no prompt, JSON only):**

```bash
renmori protect ./build/MyGame-pc --no-backup --quiet -y
```

**Force a language (e.g. in a container):**

```bash
RENMORI_LANG=en renmori protect ./build/MyGame-pc
# or: renmori protect ./build/MyGame-pc --lang en
```

**End-to-end check in a real engine (optional):**

```bash
python tools/verify_in_renpy.py --sdk /path/to/renpy-8.5.2-sdk --game /path/to/your-game
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `has no 'game/' directory` | Point renmori at the build folder that contains `game/`, not at `game/` itself or a `.zip`. |
| `is already protected` | The target already has `renmori.rmc`. Start from a fresh build (or the `_bak`). |
| `backup <dir>_bak already exists` | Remove it, or pass `--no-backup`, or use `-o` to protect a copy. |
| `strength 'x' requires the closed renmori plugin` | The open tool only does `baseline`. See below. |
| Prompt never appears in CI | By design — it only prompts on an interactive TTY. |

---

## Baseline vs. the closed plugin

This open tool runs the **baseline** pipeline only: a fixed container format and
a placeholder key embedded in the loader extension. That is enough to defeat
off-the-shelf tools (`unrpa`, `unrpyc`, …). Per-build *structural* polymorphism,
runtime key derivation, and anti-tamper are the **closed** component and are not
in this repository in any form; `--strength` values other than `baseline` are
rejected until that plugin is present. See
[architecture.md](architecture.md) and [m4.md](m4.md).

renmori targets **Ren'Py 8.x (Python 3)**. It is verified on macOS / Ren'Py
8.5.2; Windows and Linux/Steam Deck code paths exist but are not yet run on that
hardware — test on your target platform before shipping.
