# M1 results — asset layer (Windows-first, verified on macOS/arm64)

M1 built and verified the baseline asset layer: an encrypted container replacing
RPA, a runtime loader hook, and crypto backends that work inside Ren'Py's
bundled Python. Verified against **Ren'Py 8.5.2** using the SDK sample
`the_question` and a real commercial game (「冬日树下的回忆」, 1994 files, 2.1 GB).

Target is Windows; development/verification host is macOS/arm64. The Windows
runtime path (CNG) is written but verified in M4 on Windows.

## What was proven

**Every asset type decrypts byte-perfectly through the real `renpy.loader`
inside the engine** — compared to the original file's SHA-256:

| Type | Example | Path |
|------|---------|------|
| Image (PNG/JPG) | `images/bg club.jpg` (984 KB) | buffer |
| Audio (Opus) | `illurock.opus` (234 KB) | buffer |
| Script (`.rpyc`) | `script.rpyc`, `gui.rpyc` | buffer |
| Translation | `tl/schinese/script.rpyc` | buffer |
| Font (TTF) | `MaokenAssortedSans.ttf` (12 MB) | **stream** |
| Font (TTF) | `SourceHanSansLite.ttf` (2.9 MB) | buffer |
| Video (webm) | `log.webm` (43 MB) | **stream** |
| Video (ogv/avi) | `title1.ogv` (18 MB), `drs2.avi` | stream / buffer |

`lint` parses every `.rpyc` and translation from the container — the script
layer loads fully. No plaintext `.rpa`/`.rpyc`/`.rpy` remains on disk after
protection; only `renmori.rmc` + `renmori.rpe` (+ runtime `cache/`).

Reproduce:

```bash
python tools/verify_in_renpy.py --sdk /Applications/renpy-8.5.2-sdk \
    --game /Applications/renpy-8.5.2-sdk/the_question
```

## Off-the-shelf tools fail

- `unrpa -l renmori.rmc` → *"Auto-detection of the version failed … likely a
  version not supported"*. It is not an RPA.
- No `.rpyc`/`.rpy` on disk for `unrpyc` to decompile.
- Signature-carving the 2.1 GB container finds **zero** multi-byte magics
  (`PNG`, `RENPY RPC2`, `OggS`, `RIFF`, `OTTO`, `zip`). Only coincidental 3-byte
  hits (~112 `FF D8 FF`, statistically expected ≈125 over 2 GB of random-looking
  data) — nothing recoverable. The container is indistinguishable from random.

## Performance (baseline reference reader)

Sequential decrypt throughput via the **Python** reference reader (ctypes →
OpenSSL EVP in `librenpython`, AES-256-GCM per 64 KB chunk), inside Ren'Py:

| File | Size | Time | Throughput |
|------|-----:|-----:|-----------:|
| `log.webm` | 43 MB | 586 ms | ~74 MB/s |
| `MaokenAssortedSans.ttf` | 12 MB | 165 ms | ~75 MB/s |
| `title1.ogv` | 18 MB | 243 ms | ~75 MB/s |

Packing 1994 files / 2.1 GB took ~13 s.

~74 MB/s sequential is already far above video/audio decode rates (realtime
playback needs a few MB/s), and small assets hit the buffer path and then
Ren'Py's own C buffer RWops with no further per-read GIL. This is the *reference*
reader; the shipping native `SDL_RWops` decryptor removes the per-chunk Python
call overhead. A perceptual before/after frame-time comparison in an actual
playing session is still pending (needs a windowed run) and is tracked for the
benchmark harness.

## Key architecture facts established

- Clean hook points: `file_open_callbacks` (insert at front),
  `scandirfiles_callbacks` (discovery + `lower_map`); the `.rpe` extension loads
  before `index_files()`. See [loader-hook.md](loader-hook.md).
- AES inside Ren'Py with no pip deps: OpenSSL EVP exported by `librenpython` on
  macOS/Linux (found next to `sys.executable`); CNG on Windows. `_ctypes` is
  built into all three shipped runtimes.
- The `to_rwops` reopen trap is avoided: streaming objects expose no `.name`
  or `.raw`.

## Known gaps / next

- Windows CNG backend not yet run on Windows (M4).
- `renpy.exists()` (disk-only `transfn`) returns False for containerized files;
  patch pending if any sample needs it (none did so far).
- Baseline placeholder key is embedded in `autorun.py`; runtime key derivation
  is the closed component (M3/closed).
- Script layer still ships standard `.rpyc` (encrypted at rest). Custom AST
  format is M2.
- Windowed perceptual performance benchmark (frame time) pending.
