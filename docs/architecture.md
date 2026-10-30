# Architecture

RenMori is a **build-time tool** plus a **native runtime core**. It takes an
already-built Ren'Py 8.x (Python 3) distribution build and produces a protected
one. No game source changes are required.

A native launcher is only one of four layers. The others — assets, scripts,
engine — are where the actual protection lives.

## Global first principle: performance wins

Any protection measure that conflicts with runtime performance is dropped or
weakened, never the reverse. Concretely:

- **No heavy packers or VM protectors by default** (VMProtect, Themida, …) — they
  slow startup, break under Proton/Wine (Steam Deck and Linux), trip antivirus,
  and interfere with macOS notarization
- **Nothing anti-debug or self-checking on the hot path** — integrity checks run
  once, at startup
- **Symmetric, hardware-accelerated crypto only** (AES, AES-NI) — decryption is
  native (Rust or C), never a Python loop
- **Polymorphism carries the protection** because it is a build-time transform
  with *zero* runtime cost — the strategy is "not breakable in bulk", not
  "defended at runtime"
- **Acceptance line** — a protected build is indistinguishable from an
  unprotected one in frame time, scene transitions, and CG/video playback; if a
  measure cannot meet that, the measure goes, not the performance

## The four layers

### 1. Assets (every file, fonts included)

- All files under `game/` (images, audio, video, fonts, `.rpyc`, `tl/`, JSON,
  …) are packed into a **custom encrypted container**, replacing the RPA archive
  format entirely; each file carries its own key and an integrity tag
- At runtime a native module takes over `renpy.loader`'s file-open and index
  entry points and returns **decrypted, streaming** file objects; fonts
  (FreeType), video (ffmpeg), and audio all read through the loader, so a single
  choke point covers them
  - **Implementation task** — audit every resource type's read path to confirm it
    goes through `renpy.loader`, and add hooks for any that bypass it
- **Streaming, random-access decryption** by offset, so video and audio are
  never decrypted whole into memory; the container format must be
  offset-addressable
- **Decrypted results reuse Ren'Py's existing caches** (textures, audio), so the
  same image is never decrypted twice

### 2. Scripts (source obfuscation)

- Output is **not** standard `.rpyc` — a custom AST serialization is used, with
  class-name mapping, field order, and structural layout **randomized per
  build**, so pickle-based decompilers that rely on a fake `renpy` module have
  nothing stable to bind to
- Python embedded in scripts (`init python`, `$`) is compiled and encrypted at
  build time and decrypted only to execute at runtime, with debug metadata
  (source filenames, line numbers) optionally stripped
- Dialogue and strings are stored encrypted and opened only on use

### 3. Engine

- The `renpy/` engine code and the Python standard library are packed and
  encrypted, with a startup integrity check against tampering
- **Whitelist loading** — only build-time-signed scripts and modules load, and
  stray `.rpy` or `.rpyc` files dropped into the game directory are refused,
  which blocks `un.rpyc`-style injection decompilers
- Release builds disable the developer console, developer mode, and the
  data-exporting CLI subcommands (compile, lint, dialogue export, …)

### 4. Native launcher (the shell)

- A native per-platform launcher replaces Ren'Py's own — it boots the embedded
  Python, loads the engine from the encrypted container, and **derives keys at
  runtime**, leaving no plaintext key on disk
- Written in Rust or C and compiled into both a launcher and a CPython extension
  module, so the core logic lives in native code rather than Python

### 5. Per-build polymorphism (the core value)

Each build randomizes container format parameters, the AST encoding map, and the
key-derivation path, so a universal unpacker cannot exist. This is a build-time
transform and adds nothing to runtime cost.

## Open-core split

The rule: **anything public must, even if fully understood, not let anyone write
a single unpacker that works on all RenMori games.**

### Open (this repository)

- CLI skeleton, configuration parsing, CI integration, and the GitHub Actions
  sample
- The **`renpy.loader` hook framework and runtime SDK** — the plumbing that takes
  over the loader and pipes decrypted streams back to the engine; publishing it
  as open source is a *feature*, since developers can verify there is no backdoor
  or phone-home and can debug compatibility themselves
- The **baseline container format v1 specification** — a fixed, public,
  moderate-strength format
- Standard cryptographic primitive usage — AES is a public standard, so
  publishing its use costs nothing
- Documentation, samples, and tests

The open parts are usable alone, at baseline strength (a fixed, predictable
format).

### Closed (precompiled binary plugin, decided)

- The **polymorphism / mutation engine** — how each build randomizes container
  layout, field order, and AST class mapping; it runs **only at build time and
  never ships to players**, so a leak would expose the whole transform space and
  let an attacker write a generic solver, which is why it must stay closed
- The **key-derivation obfuscation** — the key is ultimately derivable on the
  client, but *how* it is derived and hidden is what raises the
  reverse-engineering cost
- The **native anti-tamper and key-recovery runtime** — shipped as a precompiled
  binary with no source; it ships with the game and is therefore ultimately
  reversible, so closing it only raises the bar

**Delivery:** the open CLI invokes the closed precompiled binary at build time.
It is CI-friendly, offline-capable, and fits free distribution. The two
communicate over a **stable, documented process interface** (CLI over
stdin/stdout, or local IPC: input is the build-artifact path plus config, output
is the protected artifact plus manifest). The interface is open; the
implementation is not. One binary per platform.

Optionally, the runtime accepts only build fingerprints signed by the official
closed binary, so a weak self-written polymorphism layer cannot impersonate it.

## Anti-reverse-engineering (honest model)

Premise: a binary that ships to players and must decrypt locally cannot be made
unbreakable — this is the white-box problem. The goal is to raise the cost, make
breaks non-portable, and rotate the scheme so old breaks age out. Success means
no universal unpacker exists and each game requires dedicated expert effort. Full
reasoning is in [threat-model.md](threat-model.md).

Two closed artifacts, with different threat models:

1. **Build-time binary** (polymorphism and key derivation) — runs only on the
   development or CI machine and **never ships to players**, so it is much easier
   to protect
2. **Runtime core** (the decryption and anti-tamper module in every shipped game)
   — runs on the attacker's machine and must decrypt everything, so it is fully
   white-box

Hardening the runtime core, by payoff (and bounded by *performance wins*):

- **All native, never Python** — any `.py` or `.pyc` of the key logic is a
  giveaway
- **Polymorphism yields non-portable breaks** (most important) — a full reverse
  of one game produces a tool for that game and version only
- **Keys are never static constants** — they are derived at runtime from several
  sources (code-segment self-hash, scattered constants, computed values) so a
  single memory dump does not yield a ready key; true white-box cryptography is
  hard and academic constructions get broken, so this is not over-promised
- **Symbol stripping and no debug information** in release builds
- **Native obfuscation** — control-flow flattening, opaque predicates, and
  instruction substitution via obfuscator-LLVM (cross-platform), *compile-time
  only, with nothing that costs runtime performance*
- **Self-integrity bound to decryption** — if the binary or engine is patched,
  key derivation yields garbage rather than a clean error, which makes a patch
  harder to diagnose (startup only)
- **Anti-debug** — minimal and off by default, because it is an arms race, false
  positives trip antivirus, and it costs performance
- **Lazy chunked decryption, freed immediately** — never holds a whole CG or
  video in plaintext in memory, which raises the cost of memory ripping without
  preventing it

Compatibility and performance verdict (already decided by performance-first):
**native code, obfuscator-LLVM (light), symbol stripping, and polymorphism**.
Heavy commercial packers remain a Windows-only, default-off option, enabled only
if measured to have no perceptible performance impact.

## Platform integration

### Steam

- **Allow the Steam overlay's injection** — the overlay injects into the game
  process, and aggressive anti-tamper or anti-injection would block it and break
  store integration; performance-first already keeps anti-tamper minimal, and the
  injection is explicitly allowed
- **Do not double-wrap with Steam DRM** — Steam's DRM wraps and edits the
  executable and can conflict with or trip the startup self-check, so either test
  compatibility or advise customers to skip Steam DRM, which is weak in any case
- Achievements and Cloud go through Ren'Py's Python API, which is untouched;
  `libsteam_api` and `steam_appid.txt` stay loadable; encrypted containers are
  static files, so Steam's file verification and updates work normally

### macOS signing / notarization (assume the developer does *not* notarize)

- **Design constraint — decrypt data only, never generate or execute decrypted
  code** — so no hardened-runtime entitlement is needed and protection does not
  force developers into paid signing, and an unsigned distribution behaves like
  any unsigned Ren'Py macOS game (Gatekeeper right-click-open)
- **Apple Silicon requires at least an ad-hoc signature to run** (`codesign -s -`,
  free, no account) — the build tool ad-hoc-signs the launcher and dylibs it
  produces by default
- If the developer has a Developer ID and wants to notarize, the binaries stay
  re-signable and hardened-runtime compatible, with a documented flow

## Licensing

- Everything — the framework and tools, the closed plugin, and the runtime
  shipped inside games — is under the **RenMori License** (`../LICENSE`; Chinese
  `../LICENSE.zh-CN.md`): free to use to protect any Ren'Py game, including a
  commercial one, with the runtime **redistributable embedded in the released
  game** at no charge, so a developer can legally sell their protected game
- Not permitted: selling RenMori itself or a modified version, or running a paid
  encryption service with it — this is a source-available license, not an OSI
  open-source license, because the no-resale term cannot be expressed under a
  permissive license
- A **CLA** is required for contributions, so contributed code can be used across
  the framework and the closed plugin under a single, consistent license
- Third-party notices in `../NOTICE` — **ffmpeg (LGPL/GPL) is the main compliance
  hazard**, along with the AES library and Ren'Py's own license
- **Security disclaimer** — states that no protection is unbreakable and limits
  liability if a game is cracked
- **Export and cryptography notice** — software containing strong encryption may
  be subject to export controls
- **Privacy statement** — no telemetry (or an honest list of what is collected),
  to dispel any suspicion that the loader hook phones home

## Milestones

- **M0** — this documentation
- **M1** — asset-layer proof of concept (Windows): encrypted container and loader
  takeover; images, audio, video, and fonts load; `unrpa`, `rpatool`, `RenPack`,
  and `RenpyEx` all fail; the protected-vs-unprotected performance benchmark on a
  CG- and video-heavy sample passes
- **M2** — script and engine layers: custom AST format, signed-whitelist loading,
  release lockdown, and refusal of injected scripts
- **M3** — single-command CLI and CI: a standard Ren'Py artifact in, a
  configuration file, exit codes, a build manifest, and a GitHub Actions sample
- **M4** — per-build polymorphism; macOS (automatic ad-hoc signing, optional
  notarization) and Linux/Steam Deck launchers; verification of the Steam
  overlay, Steamworks, and Proton/Steam Deck

## Verification

- **Functional** — the protected sample game runs and completes on all three
  platforms, with every asset and all story content correct
- **Protection** — `unrpa`, `rpatool`, `RenPack`, `RenpyEx`, and `unrpyc`
  (including `--try-harder` and `un.rpyc` injection) all fail, and no plaintext
  file is on disk at any time, fonts included
- **Performance** — the CG- and video-heavy sample meets the acceptance line
  against the unprotected build
- **Usability and CI** — one command on a clean CI runner, correct exit codes,
  and a green sample workflow
