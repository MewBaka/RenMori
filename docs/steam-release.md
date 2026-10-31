# Releasing a protected build to Steam

RenMori protects a **built** Ren'Py distribution build. Publishing to Steam is three
ordered steps, and the order matters:

```
Ren'Py launcher: Build Distributions   →   renmori protect   →   SteamPipe upload
   (from your project source)              (encrypt game/)        (upload the folder)
```

> **Do not reverse this.** If you protect first and then re-run the Ren'Py
> launcher's *Build Distributions* on your project, the launcher rebuilds from
> source and produces a fresh **unprotected** distribution build — your protection is
> gone. Protect the launcher's output, and never feed a protected folder back
> into the launcher.

This walkthrough uses the SDK sample `the_question` and its **market** build as
the example, because that one package contains all three platforms.

---

## Which build to upload

The Ren'Py launcher can produce:

- **pc** — Windows + Linux
- **mac** — macOS
- **market** — one universal package with Windows (`.exe`), macOS (`.app`), and
  Linux (`.sh`) launchers sharing a single `game/`

Both patterns work on Steam:

| Pattern | What you do | Trade-off |
|--------|-------------|-----------|
| **Market (simple)** | Protect the one market folder; put it in **one depot** mounted on all OSes; set per-OS launch options | Every player downloads all three platforms' files |
| **Per-platform (tidy)** | Build **pc** and **mac** separately, `renmori protect` each, upload each to its **own depot** (Windows / macOS / Linux) | More steps, but each player only downloads their platform |

RenMori's protection is platform-agnostic — the `renmori.rpe` loader runs inside
Ren'Py's own bundled Python on each OS — so **one `protect` run on the market
build covers Windows, macOS, and Linux at once**.

---

## Step 1 — Protect

Unzip the launcher's market archive to a folder (RenMori takes a directory, not
a `.zip`), then:

```bash
renmori protect ./the_question-7.0-market -o ./the_question-7.0-market-protected
renmori verify  ./the_question-7.0-market-protected
```

Only `game/` changes; the per-platform launchers are untouched:

```
the_question-7.0-market-protected/
├─ game/
│   ├─ renmori.rmc        # all assets, encrypted
│   ├─ renmori.rpe        # runtime loader (Ren'Py loads it automatically)
│   └─ steam_appid.txt    # kept as plaintext (the Steam SDK reads it directly)
├─ lib/                   # untouched — per-platform Python runtimes
├─ renpy/                 # untouched
├─ the_question.app/      # untouched — macOS launcher
├─ the_question.exe       # untouched — Windows launcher
├─ the_question.py
├─ the_question.sh        # untouched — Linux launcher
└─ renmori-manifest.json
```

The plaintext `.rpa`/`.rpyc` that were under `game/` are gone; `unrpa` and
`unrpyc` have nothing to work with.

---

## Step 2 — Upload with SteamPipe

Steam does **not** take a single file. A build is the **contents of a folder**,
uploaded to a depot with SteamPipe. So:

- **Do not** upload the `.zip`
- **Do not** upload only `renmori.rmc`
- **Do** point the depot's `contentroot` at the **protected folder** and let
  SteamPipe upload everything in it (`game/`, `lib/`, `renpy/`, the launchers)

`app_build_<APPID>.vdf`:

```vdf
"appbuild"
{
  "appid"       "YOUR_APPID"
  "desc"        "the_question 1.0 (renmori protected)"
  "buildoutput" "D:\steam\output\"
  "contentroot" "D:\dists\the_question-7.0-market-protected\"
  "setlive"     ""          // upload only; set the live branch in the web UI
  "depots"
  {
    "YOUR_DEPOTID"
    {
      "FileMapping" { "LocalPath" "*"  "DepotPath" "."  "recursive" "1" }
    }
  }
}
```

```bash
steamcmd +login YOUR_ACCOUNT +run_app_build "D:\steam\app_build_YOUR_APPID.vdf" +quit
```

(The Steamworks "SteamPipe GUI" does the same thing — you point it at the
protected folder.)

For **per-platform depots**, protect each platform build separately and give
each its own depot with its own `contentroot`.

---

## Step 3 — Launch options

Set these in the Steamworks web UI (*Installation → General Installation →
Launch Options*), one per OS, pointing at the launcher inside the build:

| OS | Executable |
|----|-----------|
| Windows | `the_question.exe` |
| Linux | `the_question.sh` |
| macOS | `the_question.app` |

The launcher boots Ren'Py; `renmori.rpe` takes over loading and decrypts assets
in memory. Players notice nothing.

---

## Steam specifics

- **Don't double-wrap with Steam DRM** (the DRMToolkit executable wrapper) — it
  rewrites the launcher binary, can conflict with runtime self-checks, and is
  weak on its own, whereas RenMori already protects the data layer
- **The overlay is safe (default build, without `--launcher`)** — RenMori only
  hooks Ren'Py's file loading, never process/DLL injection, so the Steam overlay
  works normally. If you build with `--launcher`, see "Native launcher and Steam"
  below
- **Achievements and Cloud saves** go through Ren'Py's Python API and are
  unaffected; `renmori.rmc` is a static file, so Steam's file verification and
  delta updates work normally
- **`steam_appid.txt`** is read by the Steam SDK outside `renpy.loader`, so
  RenMori keeps it as plaintext by default (`DEFAULT_KEEP_ON_DISK`) — keeping it
  in the shipped build is harmless, and any other externally-read files can be
  added via `keep_on_disk` in `renmori.toml`

---

## Native launcher (`--launcher`) and Steam

`--launcher` is **opt-in**. It replaces the game's entry point with the
RenMori native launcher, which performs boot attestation and then re-launches the
real engine. That re-launch changes the process model the Steam overlay and the
Steamworks SDK rely on, so its Steam compatibility is tracked per OS:

| OS | Re-launch | Status |
|----|-----------|--------|
| macOS | `execv` (same PID, inherited env) | **Verified** — the overlay re-attaches to the real engine and `SteamAPI_Init` keeps its app context; the overlay opens over the game and gameplay is smooth |
| Windows | `_spawnv` (engine runs as a child process) | **Not yet tested** — the child-process model is the case most likely to affect overlay injection; `SteamAPI_Init` should still inherit the app context |
| Linux | `execv` (same as macOS) | **Not yet tested** — expected to behave like macOS |

> **Help wanted — Windows.** The native-launcher + Steam combination has **not been
> confirmed on Windows**: whether the Steam overlay (Shift+Tab) attaches to the
> re-launched engine, and whether achievements / Cloud saves via the Steamworks SDK
> work, are **untested**. If you ship a `--launcher` build to Steam on Windows,
> please report back whether the overlay and achievements work. Until then, prefer
> the **default (no-`--launcher`) build** for Steam on Windows, or keep `--launcher`
> to macOS.

As of 1.2.5 the launcher is **auto-installed only into the macOS `.app`**. For
Windows/Linux the launcher ships as a separate file and must be wired in by hand
(rename the real engine to `<name>.renmori_real` and put the launcher at the entry
point), so a `--launcher` build is turn-key on macOS only for now.

From 1.2.5 the launcher refuses to start when it finds loose Ren'Py scripts or
extensions under `game/`, so mods or patches that players drop into `game/` as
`.rpy` files stop a `--launcher` build from starting, so ship such content inside
the build instead; builds protected with `--launcher` on 1.2.0 or earlier miss
this check and should be protected again with 1.2.5 or later.

The overlay rendering itself can feel heavy — that is Steam's own CEF layer (more
so when testing through *Add a Non-Steam Game* rather than a real store app), not
RenMori.

---

## Checklist

- [ ] Built from source in the Ren'Py launcher (Build Distributions)
- [ ] `renmori protect` on the extracted build folder
- [ ] `renmori verify` passed
- [ ] SteamPipe `contentroot` points at the **protected folder**, not a `.zip`
- [ ] Per-OS launch options set (`the_question.exe` / `.sh` / `.app`)
- [ ] No Steam DRM wrapper applied
- [ ] Did **not** re-run the launcher on the protected folder
- [ ] If using `--launcher`: verified on macOS only — Steam overlay/SDK on Windows
      is **untested** (see "Native launcher and Steam")
- [ ] If using `--launcher`: protected with 1.2.5 or later
