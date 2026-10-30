# RenMori

**Full-data protection for commercial Ren'Py visual novels**

RenMori is a build-time tool and a native runtime that takes an already-built
Ren'Py 8.x distribution and produces a protected one. Every asset — scripts,
sprites, CGs, audio, video, fonts, translations, and configuration — is packed
into an encrypted container and decrypted only inside the running engine. The aim
is twofold: the common unpacking and decompiling tools, and the agents that
merely call them, fail outright, and every build differs so that no single
unpacker works across games.

> **Status** — pre-1.0. The protection stack is built and verified; the design is
> in [docs/architecture.md](docs/architecture.md), and current progress is in the
> [roadmap](#roadmap) below.

A Chinese version of this document is in [README.zh-CN.md](README.zh-CN.md).

---

## What it protects against, and what it cannot

Read this first. A game that runs on the player's machine can never be made
uncrackable. The engine must read its own assets to run, so the keys and the
decryption logic ship with the game, and the screen can always be captured. Every
local content protection has eventually been broken, and RenMori does not claim
otherwise.

What RenMori does provide:

- off-the-shelf tools fail — `unrpa`, `rpatool`, `RenPack`, `RenpyEx`, and
  `unrpyc` (including `--try-harder` and injection decompilation) do not work on a
  protected build, which stops the large majority of extraction attempts, as those
  are someone running one of these tools
- a break does not transfer — every build uses a different container layout,
  script encoding, and key derivation, so reverse-engineering one title yields a
  tool for that one title and version, not a universal unpacker
- no plaintext on disk at any time, fonts included

If the threat model requires preventing a determined, skilled attacker from ever
extracting a single asset, no client-side tool can provide that. RenMori raises
the cost to dedicated, per-title, per-version expert effort, which is enough that
most games are never worth the work.

## Design priorities

These are in order, and a lower priority yields to a higher one:

- performance first — any protection measure that conflicts with runtime
  performance is dropped; there are no heavy packers or virtualizing protectors by
  default, encryption is hardware-accelerated and native, and integrity is checked
  once at startup rather than on the hot path, so a protected build is
  indistinguishable from an unprotected one in frame time, scene transitions, and
  CG or video playback
- easy for developers and for CI — one command over a standard Ren'Py
  distribution build, clear exit codes, configuration by file or environment, and
  a sample GitHub Actions workflow, with no change to the game's source
- protection — delivered mainly through per-build polymorphism, which carries zero
  runtime cost, rather than through runtime hardening

## How it works

Protection is applied in four layers:

| Layer | What happens |
|-------|--------------|
| Assets | every file under `game/` is packed into an encrypted container in place of RPA; a native module takes over `renpy.loader` and returns decrypted, streaming file objects, so large video and audio is decrypted per chunk by offset rather than whole into memory |
| Scripts | compiled scripts use a custom AST format in place of standard `.rpyc`, with per-build class and field remapping, so pickle-based decompilers cannot reconstruct them, and embedded Python is compiled and encrypted |
| Engine | only build-time-signed scripts load, and a stray `.rpy` or `.rpyc` dropped into the game directory is refused, which blocks injection decompilers; the developer console and the data-export subcommands are disabled in a release build |
| Launcher | a native per-platform launcher runs first, derives the keys at run time, and starts the engine, so no plaintext key is on disk |

The full design is in [docs/architecture.md](docs/architecture.md), and the honest
threat model is in [docs/threat-model.md](docs/threat-model.md).

## Usage

```bash
renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected
renmori verify  ./dist/MyGame-1.0-pc-protected
```

The command is zero-config by default, with clear exit codes and a JSON result
line for CI. An optional `renmori.toml` controls the chunk size, an exclude list,
lockdown, strength, and key sources. `protect` emits `renmori-manifest.json`,
which lists the protected files and the container fingerprint, and `verify`
re-checks a build against it. The full reference is in
[docs/usage.md](docs/usage.md); see also [docs/ci.md](docs/ci.md),
[docs/steam-release.md](docs/steam-release.md), and
[examples/renmori.toml](examples/renmori.toml).

Out of the box the tool applies the baseline format. Full protection — per-build
polymorphism, runtime key derivation, and the native core and launcher — is the
closed plugin, which `renmori protect` discovers and drives when it is present;
the contract between the two is in [docs/interface.md](docs/interface.md).

## Platforms

The targets are Windows, macOS, and Linux / Steam Deck:

- Steam — the Steam overlay injects into the game process, so it is explicitly
  allowed and anti-tamper is kept minimal; do not additionally wrap the build in
  Steam's own DRM; achievements and Cloud saves use Ren'Py's normal API and are
  unaffected — see [docs/steam-release.md](docs/steam-release.md)
- macOS — RenMori decrypts data only and never executes decrypted code, so it
  needs no hardened-runtime entitlement and does not force paid signing, and
  notarization is not required; Apple Silicon needs at least an ad-hoc signature
  to run, which the build tool applies automatically, and a Developer ID build
  stays re-signable and notarizable

## Open-core model

RenMori is open-core: the framework is free and open, and the part whose secrecy
matters is closed.

- open, in this repository — the command-line tool, the `renpy.loader` hook
  framework and runtime SDK, the baseline container format specification, the
  standard crypto-primitive usage, the CI integration, the documentation, the
  samples, and the tests; usable on its own at baseline strength
- closed, shipped as a precompiled plugin that the open tool invokes — the
  polymorphism engine, the key-derivation logic, and the anti-tamper runtime,
  which are what prevent a universal unpacker; the polymorphism engine never ships
  to players, so keeping it closed is where secrecy is meaningful

The open tool and the closed plugin communicate over a stable, documented process
interface ([docs/interface.md](docs/interface.md)); the interface is open and the
implementation is not.

## Licensing

RenMori — the framework and tools, the closed plugin, and the runtime that ships
inside a game — is under the RenMori License ([`LICENSE`](LICENSE); Chinese
[`LICENSE.zh-CN.md`](LICENSE.zh-CN.md)). Using RenMori to protect any Ren'Py game,
including a commercial one, is free, and the RenMori runtime may be redistributed
embedded in a released game at no charge. Selling RenMori itself or a modified
version, or running a paid encryption service with it, is not permitted. This is a
source-available license rather than an OSI open-source one, because the no-resale
term cannot be expressed under a permissive license.

Third-party notices are in [`NOTICE`](NOTICE), where the FFmpeg LGPL and GPL terms
warrant particular attention. No warranty of unbreakability is given; see the
license and [docs/threat-model.md](docs/threat-model.md).

## Roadmap

- [x] **M0** — documentation, in this repository's `docs/`
- [x] **M1** — asset-layer proof of concept (container, loader hook, crypto backends), verified byte-perfect in the engine on Ren'Py 8.5.2 — see [docs/m1-results.md](docs/m1-results.md)
- [x] **M2** — script transform that defeats `unrpyc` and `rpycdec`, injection blocking, and release lockdown — see [docs/script-layer.md](docs/script-layer.md)
- [x] **M3** — command-line and CI integration: `renmori.toml`, `--exclude`, environment key sources, the `verify` command, exit codes, and a GitHub Actions sample — see [docs/ci.md](docs/ci.md)
- [x] **M4** — per-build divergence, the cross-platform `.rpe` path, Steam safeguards, and the `renpy.exists` fallback — see [docs/m4.md](docs/m4.md)
- [x] **closed stack** — the polymorphism engine, runtime key derivation, native core, and native launcher, verified in the real Ren'Py engine on Linux (CI) and macOS, with the open tool driving the closed plugin over the documented interface
