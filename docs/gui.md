中文版：[gui.zh-CN.md](gui.zh-CN.md)

# Graphical interface

`renmori gui` opens a native Tkinter window for protecting, verifying and editing the configuration file without a terminal.

The GUI is available from 1.1.0 and implements no protection logic of its own: it runs the same `renmori protect` and `renmori verify` commands as the terminal in a child process, so plugin auto-download, verification and the JSON result behave exactly as they do in the CLI.

- For the full semantics of each option, see [usage.md](usage.md)
- For the configuration file, see [`examples/renmori.toml`](../examples/renmori.toml)

---

## Launching

```bash
renmori gui
renmori gui --lang en      # force the English interface
```

The interface language follows the same rules as the CLI: `--lang` first, then the `RENMORI_LANG` environment variable, then the system locale; the GUI is available in English and Chinese, and any other locale shows English.

### Requirements

Tkinter ships with CPython, so the GUI adds no dependency, and the CLI never imports Tkinter unless `renmori gui` is run; the following environments need extra handling:

| Environment | What to do |
|-------------|------------|
| Python from Debian, Ubuntu and similar distributions | Tkinter is a separate package; run `sudo apt install python3-tk` or the distribution's equivalent |
| Python from Homebrew (macOS) | Run `brew install python-tk` |
| Python from uv or python-build-standalone | Tcl/Tk data ships with the interpreter but `TCL_LIBRARY` and `TK_LIBRARY` are unset; the GUI locates and sets them on launch |
| Headless environments (SSH sessions, CI runners, containers) | No window can be opened; use the CLI instead |

When it cannot start, `renmori gui` prints the reason to stderr and exits with code 2:

| Output | Cause |
|--------|-------|
| `GUI needs Tkinter, which is not available` | The current Python lacks Tkinter; install it as shown above |
| `Cannot open a window (no display).` | No graphical display is available |

---

## Window layout

The window has three tabs, Protect, Verify and Config, with a status bar at the bottom that shows Ready and Running…, then ✓ Done or ✗ Failed when a job finishes, and the saved path after a configuration file is saved.

The Protect and Verify tabs each have a log area: when a job starts, its first line shows the full command being run (prefixed with `$`), followed by the CLI's entire output in real time, including the progress lines on stderr and the JSON result on the last line of stdout; this is the CLI's raw output and can be used directly for troubleshooting.

Only one job runs at a time, and the corresponding button is disabled while it runs; keep the window open until the job finishes.

---

## Protect

The Protect tab corresponds to `renmori protect`.

### Paths

| Field | Option | Notes |
|-------|--------|-------|
| Game build | `<game-dir \| game.zip>` | Use Folder… to pick a distribution build directory that contains `game/`, or .zip… to pick an archive produced by the launcher |
| Output (-o) | `-o, --output` | Leave empty to protect in place (backed up to `<dir>_bak` first by default); when set, the directory must not exist |

### Options

| Control | Option | Default | Notes |
|---------|--------|---------|-------|
| Strength | `--strength` | empty | Empty, `full`, `auto` or `baseline`; when empty, no option is passed and the configuration file's value applies, otherwise `full` |
| Chunk size | `--chunk-size` | empty | In bytes; when empty, the configuration file's value or the default 65536 applies |
| Platforms | `--platforms` | auto-detect | Clear auto-detect to choose from `mac-universal`, `linux-x64` and `win-x64`; clearing it without choosing a platform still auto-detects; plugin only |
| Lockdown (disable console/developer/export) | `--no-lockdown` | checked | Clearing it is equivalent to `--no-lockdown`; while checked, no option is passed and the configuration file's `lockdown` applies, otherwise on |
| Bind a native launcher (--launcher) | `--launcher` | unchecked | Plugin only |
| No backup (in-place) | `--no-backup` | unchecked | Does not create `<dir>_bak` when protecting in place; no effect when an output directory is set |
| Keep plaintext (debug) | `--keep-plaintext` | unchecked | Keeps the packed originals; for debugging only, never for a distribution build |
| Plugin path | `--plugin` | empty | Uses the given plugin binary instead of the auto-downloaded one |
| Config (-c) | `-c, --config` | empty | When empty, `<game-dir>/renmori.toml` or `renmori.toml` in the working directory is auto-detected |

The Protect tab has no exclude list or key source settings; for those, generate a `renmori.toml` on the Config tab, then select it in Config (-c) or save it into the build directory for auto-detection.

### Flow

1. Clicking Protect opens a confirmation dialog showing the input and output paths
2. Once confirmed, the GUI runs `renmori protect` with `-y`, so the CLI asks no further questions
3. On the first full protection, the plugin is **downloaded directly** without a separate prompt; it is checked against the release's `SHA256SUMS` and cached, and to stay offline set `RENMORI_PLUGIN` or `RENMORI_NO_DOWNLOAD=1` (see "Baseline and full protection" in [usage.md](usage.md))
4. When the job ends, the status bar shows ✓ Done only if the exit code is 0 and the JSON result's `status` is `ok`

The release guidance printed on success appears in the log area; the GUI does not expose `--no-hints`, `--quiet` or `--no-color`.

---

## Verify

The Verify tab corresponds to `renmori verify`: use Browse… to pick a protected build directory produced by `renmori protect`, then click Verify; it checks the same things as the CLI, namely the container hash, the presence of required files and the absence of plaintext `.rpa`, `.rpyc` and `.rpy` on disk, and the result appears as JSON at the end of the log area.

---

## Config

The Config tab is a form editor for `renmori.toml` that generates, opens and saves configuration files; it does not change the Protect tab's settings directly, so after saving, select the file in Config (-c) on the Protect tab or place it in the build directory.

### Form fields

| Control | Config key | Notes |
|---------|------------|-------|
| Strength | `[protect] strength` | Not written when empty |
| Chunk size | `[protect] chunk_size` | Not written when empty |
| Platforms | `[protect] platforms` | Not written when none is checked, in which case protection auto-detects |
| Lockdown | `[protect] lockdown` | Always written, as `true` or `false` |
| Bind a native launcher | `[protect] launcher` | Written only when checked |
| Keep plaintext (debug) | `[protect] keep_plaintext` | Written only when checked |
| Exclude globs (one per line) | `[protect] exclude` | Matching files stay unencrypted |
| Keep on disk (one per line) | `[protect] keep_on_disk` | Files left on disk for programs other than the engine to read; `steam_appid.txt` is included by default |
| Keys (baseline only) master_env | `[keys] master_env` | The **name of an environment variable**, not the key itself |
| Keys (baseline only) script_env | `[keys] script_env` | As above |

### Buttons

| Button | Action |
|--------|--------|
| Open… | Reads an existing `renmori.toml` into the form |
| Generate preview | Regenerates the configuration text in the preview area from the form |
| Save as… | Regenerates the configuration text from the form and saves it, with `renmori.toml` as the default file name |

### Notes

- The preview area is **for viewing only**: Save as… regenerates the text from the form and overwrites the preview, so manual edits in the preview are not saved
- When a file is opened, only the keys listed above are read into the form; other keys and comments are not kept on save
- Reading a configuration file needs Python 3.11+ or the `tomli` package; if the file cannot be parsed, the GUI reports why and loads the raw text into the preview for viewing
- The key fields record only environment variable names; never write a key into the configuration file, and see [ci.md](ci.md) for key management in CI

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `renmori gui` exits immediately with code 2 | Tkinter or a display is missing; see "Requirements" |
| The window is briefly blank on macOS | Tk can be slow to paint the first frame in some environments, and the GUI forces one layout refresh after launch; if it stays blank, resize the window once |
| The status bar shows ✗ Failed | Look for lines starting with `error:` in the log area and see "Troubleshooting" in [usage.md](usage.md) |
| Settings changed on the Config tab have no effect | Save the configuration file, then select it in Config (-c) on the Protect tab or place it in the build directory |
| Manual edits in the preview are lost | By design, Save as… regenerates the text from the form; for manual edits, save the file and edit it in a text editor |
