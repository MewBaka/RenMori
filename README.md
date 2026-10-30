# renmori

**Full-data protection for commercial Ren'Py games.**

renmori is a build-time tool plus a native runtime that takes an already-built
Ren'Py 8.x game and produces a protected distribution. Every asset — scripts,
sprites, CGs, audio, video, **fonts**, translations, config — is packed into
encrypted containers and decrypted only inside the running engine. The goal is
to make the common unpacking and decompiling tools (and agents that merely call
them) fail outright, and to make every build different so that no single
unpacker can ever work across games.

> **Status:** early development. See [docs/architecture.md](docs/architecture.md)
> for the design and [the roadmap](#roadmap) for what exists today.

---

## What it protects against — and what it can't

Read this before anything else. **A game that runs on the player's machine can
never be made uncrackable.** The engine must be able to read its own assets to
run, so the keys and the decryption logic ship with the game, and the screen can
always be captured. Every local DRM has eventually been broken. renmori does not
pretend otherwise.

What renmori actually buys you:

1. **Off-the-shelf tools fail.** `unrpa`, `rpatool`, `RenPack`, `RenpyEx`,
   `unrpyc` (including `--try-harder` and `un.rpyc` injection) do not work on a
   protected build. This also stops the large majority of "rip my assets"
   attempts, which are just someone running one of those tools.
2. **Breaks don't port.** Every build uses a different container layout, script
   encoding, and key derivation. Reverse-engineering one game yields a tool for
   *that game, that version* — not a universal unpacker. You are not buying
   "unbreakable"; you are buying "not breakable in bulk".
3. **No plaintext on disk, ever** — fonts included.

If your threat model requires stopping a determined, skilled attacker from ever
extracting a single asset, no client-side tool (renmori or otherwise) can give
you that. renmori raises the cost to "dedicated, per-game, per-version expert
effort", which is enough that most games are never worth cracking.

## Design priorities (in order)

1. **Performance first.** Any protection measure that conflicts with runtime
   performance is dropped. No heavy packers/VM protectors by default; encryption
   is hardware-accelerated (AES-NI) and native; integrity checks run once at
   startup, never on the hot path. A protected build must be indistinguishable
   from an unprotected one in frame time, scene transitions, and CG/video.
2. **Easy for developers / CI-friendly.** One command on a standard Ren'Py
   build artifact, clear exit codes, config via file or environment, a sample
   GitHub Actions workflow. No source changes to the game required.
3. **Protection.** Delivered mainly through per-build polymorphism (zero runtime
   cost) rather than runtime hardening.

## How it works (four layers)

| Layer | What happens |
|-------|--------------|
| **Assets** | Every file under `game/` goes into a custom encrypted container (no more RPA). A native module takes over `renpy.loader` and returns decrypted, streaming file objects. Large files (video/audio) are decrypted in chunks by offset, never whole into memory. |
| **Scripts** | Compiled scripts use a custom AST format instead of standard `.rpyc`, with per-build class/field remapping, so pickle-based decompilers cannot reconstruct them. Embedded Python is compiled and encrypted. |
| **Engine** | The engine and stdlib are packed and integrity-checked at startup. Only build-time-signed scripts load; stray `.rpy`/`.rpyc` dropped into the game dir are refused (this blocks injection decompilers). Developer console and data-export subcommands are disabled in release builds. |
| **Launcher** | A native per-platform launcher replaces Ren'Py's, boots embedded Python from the encrypted container, and derives keys at runtime. No plaintext key on disk. |

Full detail in [docs/architecture.md](docs/architecture.md). Honest threat model
in [docs/threat-model.md](docs/threat-model.md).

## Usage

```bash
renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected
renmori verify  ./dist/MyGame-1.0-pc-protected
```

Zero-config by default; clear exit codes and a JSON result line for CI. Optional
`renmori.toml` controls chunk size, an exclude list, lockdown, strength, and key
sources. `protect` emits `renmori-manifest.json` (protected files, container
fingerprint); `verify` re-checks a build against it. Full command reference in
[docs/usage.md](docs/usage.md). See also [docs/ci.md](docs/ci.md),
[docs/steam-release.md](docs/steam-release.md),
[examples/renmori.toml](examples/renmori.toml), and
[examples/github-actions-protect.yml](examples/github-actions-protect.yml).

## Platforms

Windows, macOS, and Linux / Steam Deck.

- **Steam:** the Steam overlay (which injects into the game process) is
  explicitly allowed; anti-tamper is kept minimal so it never blocks the
  overlay. Do **not** also wrap the build in Steam's own DRM. Achievements and
  Cloud saves go through Ren'Py's normal API and are unaffected. See
  [docs/steam-release.md](docs/steam-release.md) for the upload walkthrough.
- **macOS:** notarization is **not** required. renmori only decrypts *data* and
  never executes decrypted code, so it needs no hardened-runtime entitlements
  and won't force you into paid signing. Apple Silicon requires at least an
  ad-hoc signature to run at all (free, no account) — the build tool does this
  automatically. If you do have a Developer ID, the binaries stay re-signable
  and notarizable.

## Open-core model

renmori is **open-core**. The framework is free and open; the part whose secrecy
actually matters is closed.

- **Open** (this repository): the CLI, the `renpy.loader` hook framework / runtime
  SDK, the baseline container format spec (v1), standard crypto primitive usage,
  CI integration, docs, samples, tests. Usable on its own, at baseline strength.
- **Closed** (shipped as a precompiled binary plugin the open CLI invokes): the
  polymorphism engine, the key-derivation logic, and the anti-tamper runtime.
  These are what prevent a *universal* unpacker, and the polymorphism engine
  never ships to players — so keeping it closed is where secrecy is meaningful.

The open CLI and the closed binary communicate over a stable, documented process
interface. The interface is open; the implementation is not.

## Licensing

- Open-source components: **Apache-2.0**, see [`LICENSE`](LICENSE). Chosen for
  its patent grant and trademark clause. Covers the open parts only; it does not
  reach the closed binary. See [docs/architecture.md](docs/architecture.md#licensing).
- The closed binary plugin and the runtime that ships inside your game are
  covered by a separate commercial EULA, which grants you the right to
  redistribute the runtime inside your released game.
- Third-party dependency notices live in [`NOTICE`](NOTICE). Note ffmpeg's
  LGPL/GPL terms in particular.
- Contributions require a CLA (see [`CONTRIBUTING.md`](CONTRIBUTING.md)).

**No warranty of unbreakability.** See the EULA and
[docs/threat-model.md](docs/threat-model.md).

## Roadmap

- [x] **M0** — Documentation (this repo's `docs/`).
- [x] **M1** — Asset-layer PoC + container, loader hook, crypto backends; verified byte-perfect in-engine on Ren'Py 8.5.2. See [docs/m1-results.md](docs/m1-results.md).
- [x] **M2** — Script transform (defeats `unrpyc`/`rpycdec`), injection block, release lockdown. See [docs/script-layer.md](docs/script-layer.md).
- [x] **M3** — CLI polish + CI integration: `renmori.toml`, `--exclude`, env-key sources, `verify` command, exit codes, GitHub Actions sample. See [docs/ci.md](docs/ci.md).
- [~] **M4** — Baseline per-build divergence, cross-platform `.rpe` path, Steam safeguards, `renpy.exists` fallback (verified on macOS/8.5.2). The polymorphism engine and native key-deriving launcher are the closed component; live Windows/Linux/Steam runs are hardware-pending. See [docs/m4.md](docs/m4.md).

## 中文说明

See [README.zh-CN.md](README.zh-CN.md).
