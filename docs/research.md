# Research: the state of Ren'Py protection

This document records what already exists, so the project can justify not
reinventing a wheel. Date of research: 2026-10-29.

## Summary

There is **no commercial-grade, general-purpose protector for Ren'Py** that is
polymorphic per build and covers scripts, all assets, *and* the engine at once.
The gap is real, and the public tooling landscape is entirely on the *attacker*
side (unpackers and decompilers); the few protection attempts are prototypes or
cover only one layer.

## How Ren'Py's own formats work (and why they are weak)

- **`.rpa` archives** are just an index plus concatenated files, with at most a
  XOR "obfuscation" key — they are not encrypted
- **`.rpyc` scripts** are zlib-compressed pickles of the Ren'Py AST
- Ren'Py's official guidance says obfuscation only keeps out casual browsing and
  that a "moderately skilled programmer could easily crack this"; the lead
  developer closed the asset-encryption request (renpy/renpy#2546) as not
  feasible — the game must read its own assets at runtime, so whatever is needed
  to unpack ships with the game, and assets can be captured from memory or the
  screen regardless

## Attacker-side tooling (what a protected build must defeat)

| Tool | What it does | Notes |
|------|--------------|-------|
| `unrpa` | Extracts `.rpa` | Handles RPA-1.0…4.0 and variants |
| `rpatool` | Create/list/extract/edit `.rpa` | Can pack with a chosen XOR key |
| `RenPack` | GUI/CLI for RPA-2.0/3.0/3.2 incl. XOR | Reads and *rewrites* archives |
| `RenpyEx` | Pure-Rust `.rpa`/`.rpyc` extractor | **Auto-detects the key from `options.rpy`**, SHA-256 verifies, aims byte-perfect |
| `unrpyc` | Decompiles `.rpyc` | `--try-harder`, and `un.rpyc`/`bytecode.rpyb` in-process injection |
| `rpycdec` | Decompiles `.rpyc`/`.rpymc` | Builds a fake `renpy`/`store` package so pickle can deserialize |

### What `unrpyc`'s deobfuscation actually handles

From `deobfuscate.py` — important, because it tells us which naive "mods" are
useless:

- **Slot extractors** tried in turn: standard `RENPY RPC2` header; headerless
  legacy (whole file is one zlib blob); `extract_slot_headerscan` (scans for a
  36-byte header pattern when the magic is changed/shifted); `extract_slot_zlibscan`
  (**when the header is destroyed, scans for zlib start bytes `0x78` with a valid
  checksum and decompresses candidates**)
- **Layered payload decryptors** (`DECRYPTORS`), up to 10 layers, retrying a
  pickle load after each: `decrypt_zlib`, `decrypt_hex`, `decrypt_base64`,
  `decrypt_string_escape`

**Implication:** changing the magic bytes, shifting the header, or wrapping the
payload in zlib/base64/hex/escape does **not** stop unrpyc. The zlib scanner in
particular defeats header tricks. To actually break it we must leave standard
pickle/zlib behind entirely (custom AST format) *and* make the class/field layout
differ per build, so the "fake renpy module" approach has nothing to bind to.

## Prior protection attempts

- **ichfly/renpy-Asset-Protect** — protects assets only via a key-based loader
  and a companion C executable (AES + SHA-256); prototype quality, with a
  hardcoded key table and debug file writes; the author states it is **not DRM**
  and that the approach is "easily bypassed however still better than being
  dumpable without any adaptation"
- **Forum folklore** (Lemmasoft, Zhihu): rename the `.rpa`, edit the header with
  a hex editor, hide scripts inside image files, or restrict the engine to a
  whitelist of archives — all either trivially bypassed or unverified

## Official / community consensus

- renpytom (Ren'Py lead): asset encryption is "impossible" to do fully, so he
  closed the feature request; he also advises *against* obfuscation because it
  makes games hard to fix when an engine/OS update breaks them
- uyjulian (contributor): even a complicated archive format can be beaten by
  dumping from a running game's memory or the screen (cf. NinjaRipper,
  KrkrExtract); truly blocking injected extractors would need kernel-level
  anti-cheat
- unrpyc maintainers: **won't** take feature requests to deobfuscate specific
  games, explicitly because it is an "arms race"

That last point is the strategic opening for RenMori: since nobody will build
per-game support into the universal tools, **"every build is different" is by
itself a durable advantage.**

## Takeaways that shaped the design

1. Leave RPA and standard rpyc/pickle entirely — header/encoding tricks are
   already handled by `unrpyc`
2. Per-build polymorphism is the core value and, conveniently, has zero runtime
   cost — which fits the performance-first priority
3. Be honest with customers: the win is "no universal unpacker + per-game expert
   cost", not "uncrackable" — see [threat-model.md](threat-model.md)

## Sources

- Ren'Py asset-encryption request (closed as not feasible):
  https://github.com/renpy/renpy/issues/2546
- Lemmasoft, "Protect .rpa and .rpyc from unpackers and decompilers":
  https://lemmasoft.renai.us/forums/viewtopic.php?p=389272
- Historic Ren'Py Wiki, "Obfuscating Your Game":
  https://renpy.org/wiki/renpy/doc/reference/Obfuscating_Your_Game
- unrpyc: https://github.com/CensoredUsername/unrpyc
  (`deobfuscate.py` on `master`)
- rpycdec: https://github.com/cnfatal/rpycdec
- unrpa: https://pypi.org/project/unrpa/
- rpatool: https://github.com/Shizmob/rpatool
- RenPack: https://github.com/Kroste/RenPack
- RenpyEx: https://github.com/rolanfreeman6-png/RenpyEx
- ichfly/renpy-Asset-Protect: https://github.com/ichfly/renpy-Asset-Protect
