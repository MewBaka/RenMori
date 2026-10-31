# Loader hook: how RenMori plugs into Ren'Py 8.5

Findings from reading the Ren'Py **8.5.2** source (`renpy/loader.py`,
`renpy/main.py`, `renpy/script.py`, `renpy/pygame/rwobject.pyx`) and inspecting
the shipped runtimes in the SDK. Re-verify on every Ren'Py version we support.

## 1. Every asset goes through one choke point

`renpy.loader.load(name)` → `load_core(name)` → tries each function in
`renpy.loader.file_open_callbacks` in order, returning the first non-`None`
result. Default order: `config.file_open_callback`, filesystem, archives (RPA),
APK, remote.

Audit of who calls it:

| Resource | Call site |
|----------|-----------|
| Images | `loader.load()` → `pygame.image.load(f, filename)` (`display/pgrender.py`) |
| Audio **and video** | `renpy.audio.audio.load()` → `loader.load(fn, directory="audio")`; movies play through audio channels |
| Fonts | `loader.load(fn, directory="fonts")` (`text/font.py`) |
| Scripts | `.rpyc` read with `loader.load(fn, tl=False)` (`script.py`), regardless of whether the file came from disk or an index |

**Only bypass:** `renpy.exists()` uses `transfn()` and is documented as
disk-only. A game that calls `renpy.exists()` on a file we moved into the
container will see `False`. The hook patches it.

**RenMori inserts its callback at index 0** of `file_open_callbacks`, so the
container wins over anything on disk.

## 2. File discovery: `scandirfiles_callbacks`

`listdirfiles()` (used for script discovery, `renpy.list_files()`, automatic
images, and filling `loadable_cache`) is built by calling each function in
`renpy.loader.scandirfiles_callbacks` with `add(dn, fn, files, seen)`. RenMori
registers one that adds every container entry with `dn=None` (the same way
archive entries are added). This makes `loadable()` true for our files and makes
script discovery find `.rpyc` files that only exist inside the container.

## 3. Timing: hook must be installed before `index_files()`

Scripts are discovered at startup, before any game `.rpy` code runs, so a normal
`init python` block is too late. Ren'Py 8.5 has an official early hook:
**Ren'Py Extensions**. `renpy.main.main()` loads, in sorted order, every
`*.rpe` (zip containing `autorun.py`, put on `sys.path`) and `*.rpe.py` from the
Ren'Py base dir, `game/`, and `game/libs`, **before** `renpy.loader.index_files()`
and before the script is loaded.

RenMori ships its runtime as `game/renmori.rpe`. (A later version is planned
to move this into the native launcher; `.rpe` is also an attacker injection point and must be locked
down to our signed extension only.)

## 4. The return type matters: `RWopsIO` and the reopen trap

Ren'Py 8.5 hands file objects to C code (SDL_image, FreeType, ffmpeg) through
`to_rwops()` in `rwobject.pyx`. Its behavior, in order:

1. Unwraps `.raw` repeatedly
2. An `RWopsIOImpl` → its C `SDL_RWops` is used directly (**fast, no GIL**)
3. **An `io.IOBase` with a string `.name` → reopened from disk by that name** (with `.base`/`.length` if present)
4. Otherwise, anything with `read` → wrapped with Python callbacks that take the **GIL on every read**

Consequences for RenMori:

- **Trap** — a decrypting file object that subclasses `io.IOBase` and exposes a string `.name` gets reopened from disk, where it either fails to find the file or hands SDL the raw ciphertext; our stream objects must expose neither `.name` nor `.raw`
- **Small and medium files** — decrypt fully and return `RWopsIO.from_buffer(plaintext, name=name)`, a pure C buffer RWops that takes no GIL afterwards, the fastest path Ren'Py has
- **Large files (video, long background music)** — return `RWopsIO(stream, name=name)`, where `stream` decrypts chunks on demand; this path goes through Python callbacks with a GIL per read and must be benchmarked, the production answer being a native nogil decrypting `SDL_RWops` in the closed runtime

## 5. AES inside Ren'Py's own Python: no dependency needed

Ren'Py's bundled Python has no `cryptography`/`pycryptodome`, but it does ship
`ctypes` (`PyInit__ctypes` present on all three runtimes), and:

| Runtime | AES-256-GCM source |
|---------|-------------------|
| macOS (`librenpython.dylib`, universal) | OpenSSL statically linked **and exported** (`EVP_aes_256_gcm`, `EVP_CIPHER_CTX_new`, `EVP_DecryptUpdate`, …) |
| Linux (`librenpython.so`) | same, exported |
| Windows (`librenpython.dll`, `libpython3.12.dll`) | EVP symbols **not exported**; use the OS's **CNG (`bcrypt.dll`)**, which has hardware-accelerated AES-GCM on every Windows since Vista |

So the runtime reader calls OpenSSL (macOS/Linux) or CNG (Windows) through
`ctypes`. Decryption runs in native code with AES-NI / ARMv8 crypto; only the
per-chunk call overhead is Python. The build tool uses the `cryptography`
package. All backends produce standard AES-256-GCM, so the container format
does not depend on the backend.
