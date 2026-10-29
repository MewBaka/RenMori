# CLI & CI integration (M3)

renmori is a single build-time command over a standard Ren'Py build artifact —
no game source changes, no network, offline-capable.

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
the JSON.

## Options (protect)

| Flag | Config key | Default | Notes |
|------|-----------|---------|-------|
| `-o, --output DIR` | — | in place | copy to DIR first (DIR must not exist) |
| `-c, --config FILE` | — | autodetect | else `<game-dir>/renmori.toml` or `./renmori.toml` |
| `--chunk-size N` | `chunk_size` | 65536 | container chunk size |
| `--exclude GLOB` | `exclude` | none | leave matching files unencrypted (repeatable; CLI adds to config) |
| `--strength S` | `strength` | `baseline` | open tool: `baseline` only |
| `--no-lockdown` | `lockdown` | on | keep console/developer/export enabled |
| `--keep-plaintext` | `keep_plaintext` | off | debugging |
| `--quiet` | — | off | only print the final JSON |

See [`examples/renmori.toml`](../examples/renmori.toml) for the config file.

## Keys in CI

By default `protect` generates a fresh random master key and an **independent**
script key per build, embedded in the loader extension (baseline placeholder —
the closed runtime derives these instead). To manage keys yourself, point
renmori at environment variables holding 64-hex-char (32-byte) keys:

```toml
[keys]
master_env = "RENMORI_MASTER_KEY"
script_env = "RENMORI_SCRIPT_KEY"
```

Populate them from your CI secret store; never commit keys. If a named variable
is unset, renmori falls back to a random key and says so. Output is not
byte-reproducible across builds even with fixed keys (per-file random salts), by
design — assert on `verify` and the manifest's file list, not on the container
hash across builds.

## GitHub Actions

See [`examples/github-actions-protect.yml`](../examples/github-actions-protect.yml):
build → `renmori protect` → `renmori verify` → upload artifact, with keys from
`secrets`.

## End-to-end check against a real engine (optional)

[`tools/verify_in_renpy.py`](../tools/verify_in_renpy.py) protects a sample game
and confirms, inside a real Ren'Py SDK, that every asset decrypts byte-perfectly,
scripts are transformed yet parse, and injected scripts are refused. Point it at
an SDK and a game; it's skipped where no SDK is available.
