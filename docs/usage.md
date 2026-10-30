# CLI usage

The `renmori` command-line tool protects a **built** Ren'Py 8.x (Python 3)
distribution build. It makes no changes to your game's source — you run it on the
output of the Ren'Py launcher's *Build Distributions*.

- For CI pipelines and key management, see [ci.md](ci.md)
- For publishing to Steam, see [steam-release.md](steam-release.md)
- For the config file, see [`examples/renmori.toml`](../examples/renmori.toml)

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
# 1. Build your game in the Ren'Py launcher (Build Distributions).
# 2. Protect the build. The input is the built folder OR the .zip the launcher made:
renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected
renmori protect ./dist/MyGame-1.0-pc.zip          # unzips it for you

# 3. Check it:
renmori verify ./dist/MyGame-1.0-pc-protected
```

The input is any directory that contains a `game/` subdirectory, or a `.zip` of
one (the launcher's `*-pc.zip`, `*-mac.zip`, etc.). A `.zip` is extracted next to
itself — into a sibling folder named after the archive, or into `-o OUTPUT` — and
the archive is left untouched as your original, so no `_bak` is made. `protect` packs
everything under `game/` into `game/renmori.rmc`, transforms the compiled
scripts, deletes the plaintext originals, writes the loader extension
`game/renmori.rpe`, and emits `renmori-manifest.json`.

---

## Commands

### `renmori protect <game-dir | game.zip> [options]`

Protect a distribution build. The argument is the built directory, or a `.zip` of
one — a `.zip` is extracted first (see "Quick start").

- **In place (default):** overwrites the directory, but first copies the
  original to a sibling `<dir>_bak` — on an interactive terminal it prints a
  summary and asks `[y/N]` before touching anything
- **To a new directory:** `-o OUTPUT` protects a copy and leaves the original
  untouched (no backup is made in this mode)

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
| `--strength S` | `strength` | full | the default is full protection (the plugin is auto-downloaded if absent); `baseline` forces the open format; `auto` is full-when-available, else baseline (see below) |
| `--plugin PATH` | — | `$RENMORI_PLUGIN` | use this plugin binary instead of the auto-downloaded one |
| `--platforms LIST` | `platforms` | auto-detect | plugin only: comma list of target platforms, else detected from the build's `lib/py3-*` |
| `--launcher` | `launcher` | off | plugin only: bind the keys to a native launcher and ship it |
| `--no-lockdown` | `lockdown` | on | keep console/developer/export enabled |
| `--no-backup` | — | off | protect in place without the `<dir>_bak` copy (no effect with `-o`) |
| `--keep-plaintext` | `keep_plaintext` | off | don't delete packed originals (debug) |
| `-y, --yes` | — | off | skip the pre-protect confirmation prompt |
| `--no-hints` | — | off | don't print the "package & publish" guidance on success |

## Common options (both commands)

| Flag | Default | Notes |
|------|---------|-------|
| `--lang {auto,en,zh}` | `auto` | language of the human-facing output; `auto` follows the system locale; also `RENMORI_LANG` |
| `--no-color` | off | disable ANSI color — auto-off when not a terminal, and honors `NO_COLOR` |
| `--quiet` | off | suppress all styled stderr output; print only the final JSON line |

---

## Output and exit codes

Human-facing progress (the banner, summary panel, step lines, result panel, and
release hints) goes to **stderr**, styled and localized. The **last line of
stdout is always a JSON object** with stable English keys:

```json
{"status": "ok", "output": "…", "manifest": {"file_count": 842, "container_sha256": "…", "strength": "baseline"}, "backup": "…"}
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
| `has no 'game/' directory` | Point RenMori at the build folder that contains `game/` (or its `.zip`), not at `game/` itself |
| `no 'game/' directory found in the archive` | The `.zip` is not a Ren'Py build — pass the launcher's distribution archive, which holds `game/` |
| `the archive holds more than one game build` | The `.zip` bundles several builds — unzip it and point RenMori at the one you want |
| `is already protected` | The target already has `renmori.rmc`; start from a fresh build (or the `_bak`) |
| `backup <dir>_bak already exists` | Remove it, or pass `--no-backup`, or use `-o` to protect a copy |
| `full protection needs the closed plugin` | The plugin download was declined or disabled; let it download, set `--plugin` / `$RENMORI_PLUGIN`, or use `--strength baseline` (see below) |
| `Downloaded plugin failed its checksum` | The binary did not match the release's `SHA256SUMS`; retry, or check `RENMORI_PLUGIN_BASE_URL` |
| Prompt never appears in CI | By design — it only prompts on an interactive TTY |

---

## Baseline and full protection

**Full protection** — per-build structural polymorphism, runtime key derivation,
a native core, and an optional native launcher — is the **closed** component:
only the source is closed; the plugin itself is a free prebuilt binary. It is the
**default**, and you do not install it by hand. The first time you run a full
protect, `renmori` downloads the plugin for your platform from the public release,
verifies it against the release's `SHA256SUMS`, and caches it:

```bash
renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected
# first run, on a terminal:
#   ? Full protection needs the closed plugin. Download renmori-plugin-… ? [Y/n]
```

On a terminal it asks first; in CI (or with `-y` / `--quiet`) it downloads without
asking. The binary is cached under `~/.cache/renmori/` (`%LOCALAPPDATA%\renmori\`
on Windows), so later builds need no network. To control it:

| Env var | Effect |
|---------|--------|
| `RENMORI_PLUGIN` | path to a plugin you already have — skips the download entirely (same as `--plugin`) |
| `RENMORI_NO_DOWNLOAD=1` | never download; fail (or fall back, with `auto`) if the plugin is absent |
| `RENMORI_PLUGIN_BASE_URL` | pull the binary and `SHA256SUMS` from here instead of the public release (for an air-gapped mirror) |
| `RENMORI_PLUGIN_TAG` | which release tag to fetch |

With no plugin and downloads disabled, a full protect **fails** rather than
silently shipping the weaker baseline.

The **baseline** pipeline — a fixed container format with a placeholder key in
the loader extension — is a deliberate opt-in via `--strength baseline`. It
defeats off-the-shelf tools such as `unrpa` and `unrpyc`, but the key and the
reader ship in the clear, so it is not real protection against a determined
attacker. Pass `--strength auto` for the graceful behavior of full when a plugin
is present and baseline otherwise. `--platforms` and `--launcher` apply only to
the plugin, and the process contract is specified in
[interface.md](interface.md).

Either pipeline handles a game built with the launcher's archives: a `.rpa`
archive is unpacked during protection and its entries are packed into the
container as individual files, so the engine still finds the scripts and assets
once the archive is gone.

RenMori targets **Ren'Py 8.x (Python 3)**. The runtime is verified in the actual
Ren'Py engine on Linux (CI, headless) and macOS, and the Windows and Linux
runtimes are exercised by the unit, golden-container, and key-derivation jobs on
each platform; a run on Steam Deck under Proton is still pending. Test on your
target platform before shipping.
