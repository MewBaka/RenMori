# Plugin interface

RenMori is open-core. The open `renmori` command-line tool is the integration point: it parses configuration, prepares the output and backup, drives the user-facing flow, and includes the open baseline container format. The strong protection — the per-build polymorphism engine, runtime key derivation, and the native core and launcher — lives in a closed plugin that is distributed as a prebuilt component and never as source.

This document defines the stable process contract between the two. The contract is public so that the open tool and the closed plugin can be versioned and released independently; only the plugin's implementation is closed.

## Discovery

The open tool locates the plugin, in order:

- the `--plugin <path>` argument to `renmori protect`
- the `RENMORI_PLUGIN` environment variable
- the local cache, keyed by the plugin release tag (`$XDG_CACHE_HOME/renmori/plugin/<tag>` or `~/.cache/renmori/plugin/<tag>`; `%LOCALAPPDATA%\renmori\plugin\<tag>` on Windows)
- a download of the asset for the host platform from the public release, verified against its `SHA256SUMS` and then cached (skipped when `RENMORI_NO_DOWNLOAD` is set; `RENMORI_PLUGIN_BASE_URL` and `RENMORI_PLUGIN_TAG` override the source and tag)

Discovery is skipped entirely when `strength` is `baseline`. `<path>` is an executable, or a `.py` script that the open tool runs with the current Python interpreter. A plugin is used only after a successful `capabilities` handshake (below); a plugin that fails the handshake is treated as absent.

When no usable plugin is found, the outcome depends on the requested `strength`:

- unset (the default, full protection) — the run fails rather than silently shipping the baseline
- `auto` — the tool falls back to the baseline format
- any other non-baseline value — the run fails

## Transport

Every call is one short-lived subprocess. The first argument selects the operation. The request, when one is needed, is a single JSON object on **stdin**; the response is a single JSON object on **stdout**. All human-readable logging goes to **stderr**, so stdout stays machine-parsable. The exit code is 0 on success and non-zero on failure. All field names and enumerated values are ASCII and locale-independent.

Both objects carry an `interface` integer. The open tool sends the highest version it supports and refuses a plugin whose `capabilities` do not include that version.

## Operations

### `capabilities`

No request body. The plugin prints a JSON object describing itself and exits 0:

| Field | Meaning |
|-------|---------|
| `interface` | highest interface version the plugin supports |
| `name` | plugin display name |
| `version` | plugin release version |
| `strengths` | the `strength` values the plugin accepts, strongest first |
| `platforms` | the target platform keys the plugin can produce |

### `protect`

The request object on stdin:

| Field | Meaning |
|-------|---------|
| `interface` | interface version chosen by the open tool |
| `source_dir` | the built distribution to read; the plugin must not modify it |
| `output_dir` | where the protected build is written; the plugin creates it and it must not already exist |
| `strength` | one of the plugin's advertised `strengths` |
| `platforms` | an explicit list of target platform keys, or `null` to auto-detect from `source_dir/lib/py3-*` |
| `launcher` | whether to bind the keys to a native launcher and ship it |
| `exclude` | game-relative globs to leave outside the container |
| `chunk_size` | container chunk size in bytes, or `null`; the current plugin picks a per-build chunk size and ignores it |
| `lockdown` | whether to disable the developer console, developer mode, and data-export subcommands in the build |
| `keys` | an object; reserved for key material or key-source directives, empty by default |

The plugin copies `source_dir` to `output_dir`, packs every asset and script into the polymorphic container, ships each target platform's native core (and launcher, when requested), writes the runtime extension, removes the plaintext originals it packed, and prints the response object on stdout:

| Field | Meaning |
|-------|---------|
| `interface` | interface version of this response |
| `status` | `"ok"` |
| `strength` | the strength actually applied |
| `platforms` | the target platform keys produced |
| `container` | the container file name under `game/` |
| `container_sha256` | hex SHA-256 of the container |
| `files` | number of entries packed |
| `scripts` | number of scripts transformed |
| `cores` | one `{platform, filename}` per shipped native core |
| `launcher` | per-platform launcher file names, or `null` |

On failure the plugin prints `{"interface": N, "status": "error", "message": "<reason>"}` and exits non-zero. The open tool reports the message and exits with its runtime-failure code without leaving a partial `output_dir` it can avoid.

## Division of responsibility

- the open tool owns: argument and `renmori.toml` parsing, the output/backup decision and any copy or move it entails, the pre-flight summary and confirmation, the manifest it writes from the response, and all localized output
- the plugin owns: the container format and its per-build randomization, key derivation, the native core and launcher, and the exact on-disk result under `output_dir`

In-place protection is expressed to the plugin as a plain `source_dir` → `output_dir` pair: the open tool moves the original aside first (to the backup, or to a temporary directory discarded afterwards) and names the original path as `output_dir`, so the plugin never needs an in-place mode.

## Versioning and integrity

`interface` is incremented only on a breaking change to the request or response shape. A plugin may support several versions at once; the open tool selects the highest it shares with the plugin. Additive, optional fields do not bump the version.

A build produced by the plugin is intended to be distinguishable from one a third party assembles with the open framework and a hand-written weak engine: the manifest may carry a build fingerprint the runtime checks. That binding is defined with the closed component and is out of scope for this public contract.
