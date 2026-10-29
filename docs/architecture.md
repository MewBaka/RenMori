# Architecture

renmori is a **build-time tool** plus a **native runtime core**. It takes an
already-built Ren'Py 8.x (Python 3) distribution and produces a protected one.
No game source changes are required.

A shell/launcher is only one of four layers. The others — assets, scripts,
engine — are where the actual protection lives.

## Global first principle: performance wins

Any protection measure that conflicts with runtime performance is dropped or
weakened, never the reverse. Concretely:

- **No heavy packers / VM protectors by default** (VMProtect, Themida, …). They
  slow startup, break under Proton/Wine (i.e. Steam Deck and Linux), trip
  antivirus, and interfere with macOS notarization.
- **Nothing anti-debug or self-checking on the hot path.** Integrity checks run
  once, at startup.
- **Symmetric, hardware-accelerated crypto only** (AES, AES-NI). Decryption is
  native (Rust/C); never a Python loop.
- **Polymorphism carries the protection** because it is a build-time transform
  with *zero* runtime cost. The strategy is "not breakable in bulk", not
  "defended at runtime".
- **Acceptance line:** a protected build is indistinguishable from an
  unprotected one in frame time, scene transitions, and CG/video playback. If a
  measure can't meet that, the measure goes — not the performance.

## The four layers

### 1. Assets (every file, fonts included)

- All files under `game/` (images, audio, video, fonts, `.rpyc`, `tl/`, JSON,
  …) are packed into a **custom encrypted container** — RPA is abandoned
  entirely. Each file has its own key and an integrity tag.
- At runtime a native module takes over `renpy.loader`'s file-open and index
  entry points and returns **decrypted, streaming** file objects. Fonts
  (FreeType), video (ffmpeg), and audio all read through the loader, so one
  choke point covers them.
  - **Implementation task:** audit every resource type's read path to confirm it
    goes through `renpy.loader`; add hooks for any that bypass it.
- **Streaming / random-access decryption** by offset, so video and audio are
  never decrypted whole into memory. The container format must be
  offset-addressable.
- **Decrypted results reuse Ren'Py's existing caches** (textures, audio) so the
  same image is never decrypted twice.

### 2. Scripts (source obfuscation)

- Output is **not** standard `.rpyc`. A custom AST serialization is used, with
  class-name mapping, field order, and structural layout **randomized per
  build**. Pickle-based decompilers that rely on a fake `renpy` module have
  nothing stable to bind to.
- Python embedded in scripts (`init python`, `$`) is compiled and encrypted at
  build time, decrypted to execute at runtime. Optionally strip debug metadata
  (source filenames, line numbers).
- Dialogue and strings are stored encrypted, opened on use.

### 3. Engine

- The `renpy/` engine code and the Python stdlib are packed and encrypted, with
  a startup integrity check against tampering.
- **Whitelist loading:** only build-time-signed scripts/modules load. Stray
  `.rpy`/`.rpyc` dropped into the game directory are refused — this is what
  blocks `un.rpyc`-style injection decompilers.
- Release builds disable the developer console, developer mode, and
  data-exporting CLI subcommands (compile, lint, dialogue export, …).

### 4. Native launcher (the shell)

- A native per-platform launcher replaces Ren'Py's own: it boots embedded
  Python, loads the engine from the encrypted container, and **derives keys at
  runtime** — no plaintext key on disk.
- Written in Rust or C, compiled into both a launcher and a CPython extension
  module. Core logic lives in native code, not Python.

### 5. Per-build polymorphism (the core value)

Each build randomizes container format parameters, the AST encoding map, and the
key-derivation path, so a universal unpacker cannot exist. This is a build-time
transform and adds nothing to runtime cost.

## Open-core split

The rule: **anything public must, even if fully understood, not let someone
write one unpacker that works on all renmori games.**

### Open (this repository)

- CLI skeleton, config parsing, CI integration, GitHub Actions sample.
- The **`renpy.loader` hook framework / runtime SDK** — the plumbing that takes
  over the loader and pipes decrypted streams back to the engine. Open source
  here is a *feature*: developers can verify there is no backdoor or phone-home,
  and debug compatibility themselves.
- The **baseline container format v1 spec** — a fixed, public, moderate-strength
  format.
- Standard crypto primitive usage (AES is a public standard; publishing its use
  costs nothing).
- Docs, samples, tests.

The open parts are usable alone, at baseline strength (fixed, predictable
format).

### Closed (precompiled binary plugin, decided)

- The **polymorphism / mutation engine** — how each build randomizes container
  layout, field order, AST class mapping. The crown jewel: it runs **only at
  build time and never ships to players**, so if it leaked an attacker could
  understand the whole transform space and write a generic solver. Must be
  closed.
- The **key-derivation obfuscation** — the key is ultimately derivable on the
  client, but *how* it is derived and hidden is what raises reverse-engineering
  cost.
- The **native anti-tamper / key-recovery runtime** — shipped as a precompiled
  binary, no source. It ships with the game and is therefore ultimately
  reversible; closing it only raises the bar.

**Delivery:** the open CLI invokes the closed precompiled binary at build time.
CI-friendly, offline-capable, fits free distribution. The two communicate over a
**stable, documented process interface** (CLI / stdin-stdout or local IPC:
in = build-artifact path + config, out = protected artifact + manifest). The
interface is open; the implementation is not. One binary per platform.

Optionally, the runtime accepts only build fingerprints signed by the official
closed binary, so a weak self-written polymorphism layer can't impersonate it.

## Anti-reverse-engineering (honest model)

Premise: a binary that ships to players and must decrypt locally cannot be made
unbreakable (the white-box problem). Goal = raise cost + make breaks
non-portable + rotate so old breaks age out. Success = no universal unpacker;
each game needs dedicated expert effort. Full reasoning in
[threat-model.md](threat-model.md).

Two closed artifacts, different threat models:

1. **Build-time binary** (polymorphism + key derivation): runs only on the
   dev/CI machine, **never ships to players**. Much easier to protect.
2. **Runtime core** (the decrypt / anti-tamper module in every shipped game):
   runs on the attacker's machine, must decrypt everything — fully white-box.

Hardening the runtime core, by payoff (and bounded by *performance wins*):

- **All native, never Python.** Any `.py`/`.pyc` of the key logic is a giveaway.
- **Polymorphism = non-portable breaks** (most important). A full reverse of one
  game yields a tool for that game/version only.
- **Keys are never static constants** — derived at runtime from several sources
  (code-segment self-hash, scattered constants, computed values) so a single
  memory dump doesn't yield a ready key. (True white-box crypto is hard and
  academic builds get broken — don't over-promise.)
- **Symbol stripping, no debug info** in release.
- **Native obfuscation**: control-flow flattening, opaque predicates,
  instruction substitution — via obfuscator-LLVM (cross-platform). *Compile-time
  only; nothing that costs runtime performance.*
- **Self-integrity bound to decryption**: if the binary/engine is patched, key
  derivation yields garbage rather than a clean error — harder to diagnose a
  patch. (Startup only.)
- **Anti-debug**: minimal and off by default; it's an arms race, false-positives
  trip antivirus, and it costs performance.
- **Lazy chunked decryption, freed immediately**: never hold a whole CG/video in
  plaintext in memory. Raises memory-ripping cost (doesn't prevent it).

Compatibility/performance verdict (already decided by performance-first):
**native + obfuscator-LLVM light + symbol strip + polymorphism**. Heavy
commercial packers are a Windows-only, default-off option, enabled only if
measured to have no perceptible performance impact.

## Platform integration

### Steam

- **Allow the Steam overlay's injection.** The overlay injects into the game
  process; aggressive anti-tamper/anti-injection would block it (a
  store-blocker). Performance-first already keeps anti-tamper minimal; here we
  explicitly allow the injection.
- **Don't double-wrap with Steam DRM.** Steam's DRM wraps/edits the executable
  and can conflict with or trip our startup self-check. Either test
  compatibility or advise customers to skip Steam DRM (it is weak anyway).
- Achievements/Cloud go through Ren'Py's Python API (untouched); `libsteam_api`
  and `steam_appid.txt` stay loadable; encrypted containers are static files, so
  Steam's file verification and updates work normally.

### macOS signing / notarization (assume the developer does *not* notarize)

- **Design constraint: decrypt data only, never generate/execute decrypted
  code.** Then no hardened-runtime entitlement is needed and protection won't
  force developers into paid signing. An unsigned distribution behaves like any
  unsigned Ren'Py Mac game (Gatekeeper right-click-open).
- **Apple Silicon requires at least an ad-hoc signature to run** (`codesign -s -`,
  free, no account). The build tool ad-hoc-signs the launcher/dylibs it produces,
  by default.
- If the developer has a Developer ID and wants to notarize, our binaries stay
  re-signable and hardened-runtime compatible, with a documented flow.

## Licensing

- Open components: **Apache-2.0**, see `../LICENSE`. Chosen for its patent grant
  and trademark clause. Covers open parts only; does not reach the closed binary.
- Closed binary + the runtime shipped inside customer games: a separate
  commercial **EULA** that **explicitly grants redistribution of the runtime
  inside the released game** (without it, customers can't legally sell their
  game).
- **CLA** required for contributions, so community code can be used in the closed
  commercial build and the license can change.
- Third-party notices in `../NOTICE` — **ffmpeg (LGPL/GPL) is the compliance
  landmine**; also the AES library and Ren'Py's own license.
- **Security disclaimer**: "no protection is unbreakable"; limits liability if a
  game is cracked.
- **Export/crypto notice**: software containing strong encryption may be subject
  to export controls.
- **Privacy statement**: no telemetry (or an honest list), to dispel
  "loader hook phones home" suspicion.

## Milestones

- **M0** — This documentation.
- **M1** — Asset-layer PoC (Windows): encrypted container + loader takeover;
  images/audio/video/fonts load; `unrpa`/`rpatool`/`RenPack`/`RenpyEx` all fail;
  protect-vs-unprotected performance benchmark on a CG/video-heavy sample passes.
- **M2** — Script & engine layers: custom AST format, signed-whitelist loading,
  release lockdown, refuse injected scripts.
- **M3** — Single-command CLI + CI: standard Ren'Py artifact in, config file,
  exit codes, build manifest, GitHub Actions sample.
- **M4** — Per-build polymorphism; macOS (auto ad-hoc sign, optional
  notarization) and Linux/Steam Deck launchers; verify Steam overlay,
  Steamworks, Proton/Steam Deck.

## Verification

- **Functional:** protected sample game runs and completes on all three
  platforms; every asset and all story content correct.
- **Protection:** `unrpa` / `rpatool` / `RenPack` / `RenpyEx` /
  `unrpyc` (incl. `--try-harder` and `un.rpyc` injection) all fail; no plaintext
  file on disk at any time (fonts included).
- **Performance:** CG/video-heavy sample meets the acceptance line vs.
  unprotected.
- **Usability/CI:** one command on a clean CI runner, correct exit codes, sample
  workflow green.
