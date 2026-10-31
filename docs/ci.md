# CLI & CI integration (M3)

RenMori is a single build-time command over a standard Ren'Py build artifact,
with no game source changes. Full protection (the default) uses the closed
plugin, which is downloaded once from the public release and then cached; see
[Protection strength and the plugin](#protection-strength-and-the-plugin) for
fully offline runners.

## Commands

```bash
renmori protect <game-build-dir> [-o OUTPUT] [options]
renmori verify  <protected-dir>
```

`protect` packs everything under `game/` into `game/renmori.rmc`, transforms
compiled scripts, removes the plaintext originals, writes the loader extension
`game/renmori.rpe`, and emits `renmori-manifest.json`. `verify` re-checks a
protected build against that manifest (container hash, required files, no
plaintext left) — use it as a CI gate.

Protecting in place (no `-o`) overwrites the original, so RenMori first copies
it to a sibling `<dir>_bak` directory; the run fails if `<dir>_bak` already
exists. Pass `--no-backup` to overwrite without that copy. With `-o OUTPUT` the
original is never touched (the copy is protected), so no backup is made.

Input is whatever your Ren'Py build produces: any directory containing a
`game/` subdirectory.

### Exit codes

| Code | Meaning |
|-----:|---------|
| 0 | success |
| 2 | usage / precondition (no `game/`, already protected, bad config/flags) |
| 1 | runtime failure (packing error, verify mismatch) |

The final line of stdout is always a JSON object (`{"status": "ok", …}` or
`{"status": "error", …}`); progress goes to stderr. Use `--quiet` to emit only
the JSON. The styled stderr output and its language never affect stdout: the
JSON keys and values stay English in every locale, so CI parsing is stable.

Protecting in place prints a summary and asks for confirmation (`[y/N]`) — but
**only on an interactive terminal**. When stdin is not a TTY (CI), or with
`--quiet` or `-y/--yes`, it proceeds without prompting, so pipelines never hang.
Color is auto-disabled off a TTY and honors `NO_COLOR`. The output language
follows the system locale; pin it with `--lang en|zh` or `RENMORI_LANG`.

## Options (protect)

| Flag | Config key | Default | Notes |
|------|-----------|---------|-------|
| `-o, --output DIR` | — | in place | copy to DIR first (DIR must not exist) |
| `-c, --config FILE` | — | autodetect | else `<game-dir>/renmori.toml` or `./renmori.toml` |
| `--chunk-size N` | `chunk_size` | 65536 | container chunk size (baseline only) |
| `--exclude GLOB` | `exclude` | none | leave matching files unencrypted (repeatable; CLI adds to config) |
| `--strength S` | `strength` | full | unset = the plugin's strongest (fails without a plugin); `auto` = full, else baseline; `baseline` = open format, never downloads |
| `--plugin PATH` | — | autodetect | closed plugin path (else `RENMORI_PLUGIN`, the cache, then a download) |
| `--platforms LIST` | `platforms` | auto-detect | plugin only: comma list of target platforms |
| `--launcher` | `launcher` | off | plugin only: bind keys to a native launcher and ship it |
| `--no-lockdown` | `lockdown` | on | keep console/developer/export enabled |
| `--no-backup` | — | off | skip the default `<dir>_bak` copy when protecting in place (no effect with `-o`) |
| `--keep-plaintext` | `keep_plaintext` | off | debugging (baseline only) |
| `-y, --yes` | — | off | skip the pre-protect confirmation prompt |
| `--no-hints` | — | off | don't print the "create a release build" guidance on success |
| `--lang {auto,en,zh}` | — | `auto` | language of the human-facing output (also `RENMORI_LANG`); `auto` follows the system locale |
| `--no-color` | — | off | disable ANSI color (also honors `NO_COLOR`) |
| `--quiet` | — | off | only print the final JSON (no styled output on stderr) |

See [`examples/renmori.toml`](../examples/renmori.toml) for the config file.

## Protection strength and the plugin

With `strength` unset, `protect` uses the strongest strength the closed plugin
reports and **fails** (exit 2) if no plugin is available, rather than silently
shipping the weak baseline. `--strength auto` keeps the full-else-baseline
fallback; `--strength baseline` forces the open format and never downloads.

The plugin is looked up in this order: `--plugin`, `RENMORI_PLUGIN`, the local
cache (`~/.cache/renmori/plugin/<tag>`, or `%LOCALAPPDATA%\renmori\plugin\<tag>`
on Windows), and finally a download from the public release, verified against
`SHA256SUMS`. In CI the download proceeds without a prompt. Cache that directory
between runs to avoid re-downloading. On an offline runner, provision the plugin
and point `RENMORI_PLUGIN` at it, or set `RENMORI_NO_DOWNLOAD=1` to forbid any
download. `RENMORI_PLUGIN_BASE_URL` and `RENMORI_PLUGIN_TAG` select a mirror and
a release tag.

## Keys in CI

The `[keys]` section applies to the **baseline format only**. The closed plugin
derives its own keys and ignores it, so under full protection (the default) the
key environment variables below have no effect.

By default `protect` generates a fresh random master key and an **independent**
script key per build, embedded in the loader extension (baseline placeholder —
the closed runtime derives these instead). To manage keys yourself, point
RenMori at environment variables holding 64-hex-char (32-byte) keys:

```toml
[keys]
master_env = "RENMORI_MASTER_KEY"
script_env = "RENMORI_SCRIPT_KEY"
```

Populate them from your CI secret store; never commit keys. If a named variable
is unset, RenMori falls back to a random key and says so. Output is not
byte-reproducible across builds even with fixed keys (per-file random salts), by
design — assert on `verify` and the manifest's file list, not on the container
hash across builds.

## GitHub Actions

See [`examples/github-actions-protect.yml`](../examples/github-actions-protect.yml):
build → `renmori protect` → `renmori verify` → upload artifact, with the plugin
cached between runs.

## End-to-end check against a real engine (optional)

[`tools/verify_in_renpy.py`](../tools/verify_in_renpy.py) protects a sample game
and confirms, inside a real Ren'Py SDK, that every asset decrypts byte-perfectly,
scripts are transformed yet parse, and injected scripts are refused. Point it at
an SDK and a game; it's skipped where no SDK is available.
