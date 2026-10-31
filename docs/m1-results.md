# M1 results — asset layer

M1 delivered and verified the baseline asset layer: an encrypted container that replaces the Ren'Py RPA archive, a runtime loader hook, and crypto backends that run inside Ren'Py's bundled Python. Verification used Ren'Py 8.5.2, exercised with both the SDK sample project `the_question` and a gigabyte-class distribution build of thousands of assets, so that every asset type and the streaming path were covered.

The target platform is Windows; the development and verification host is macOS/arm64. The Windows runtime path (CNG) is written and verified separately under M4.

## What was proven

Every asset type decrypts byte-identically through the real `renpy.loader` inside the engine, compared against each original file's SHA-256:

| Asset type | Delivery path |
|------------|---------------|
| Image — sprite, CG (PNG/JPG) | buffer |
| Audio (Opus/OGG) | buffer |
| Script (`.rpyc`) | buffer |
| Translation (`tl/<language>/`) | buffer |
| Font, small (TTF) | buffer |
| Font, large — multi-MB (TTF) | stream |
| Video, large — WebM/OGV/AVI | stream |

`lint` parses every `.rpyc` and translation from the container, so the script layer loads in full. After protection, no plaintext archive, `.rpyc`, or `.rpy` remains on disk — only `renmori.rmc` and `renmori.rpe`, plus the runtime `cache/`.

## Off-the-shelf tools fail

- `unrpa` rejects the container: version auto-detection fails, because it is not an RPA archive
- no `.rpyc` or `.rpy` remains on disk for `unrpyc` to decompile
- signature-carving a gigabyte-class container finds zero multi-byte magics (`PNG`, `RENPY RPC2`, `OggS`, `RIFF`, `OTTO`, `zip`), leaving only the statistically expected rate of coincidental three-byte hits, none recoverable — the container is indistinguishable from random data

## Performance — baseline reference reader

Sequential decrypt throughput through the Python reference reader (ctypes → OpenSSL EVP in `librenpython`, AES-256-GCM per 64 KB chunk), measured inside Ren'Py on multi-MB assets, is approximately 74 MB/s. That is far above realtime video and audio decode rates, which need only a few MB/s. Small assets take the buffer path and then Ren'Py's own C-buffer RWops, with no further per-read GIL contention.

This is the reference reader; the shipping native decryptor removes the per-chunk Python call overhead. A perceptual before/after frame-time comparison in an actual playing session is tracked separately in the benchmark harness.

## Key architecture facts established

- hook points: `file_open_callbacks` (inserted at the front) and `scandirfiles_callbacks` (discovery plus `lower_map`); the `.rpe` extension loads before `index_files()` — see [loader-hook.md](loader-hook.md)
- AES inside Ren'Py with no third-party dependencies: OpenSSL EVP exported by `librenpython` on macOS/Linux (located next to `sys.executable`), CNG on Windows; `_ctypes` is built into all three shipped runtimes
- the `to_rwops` reopen trap is avoided: streaming objects expose neither `.name` nor `.raw`

## Known gaps / next

- ~~`renpy.exists()` (disk-only `transfn`) returns False for containerized files~~ — resolved in M4: it now also consults the container (`_install_exists_fallback`, see [m4.md](m4.md))
- the baseline placeholder key is embedded in `autorun.py`; runtime key derivation is the closed component
- ~~the baseline script layer still ships standard `.rpyc`~~ — superseded by M2: the baseline now replaces each `.rpyc` pickle payload with AES-GCM ciphertext under an independent script key (see [script-layer.md](script-layer.md)); the custom AST format remains the closed polymorphism layer
- the windowed perceptual performance benchmark (frame time) is tracked in the benchmark harness
