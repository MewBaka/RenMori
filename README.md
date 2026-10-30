<div align="center">

![English](https://img.shields.io/badge/README-English-orange?style=for-the-badge) [![简体中文](https://img.shields.io/badge/README-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-lightgrey?style=for-the-badge)](README.zh-CN.md)

</div>

# RenMori

**Full-data protection for commercial Ren'Py visual novels.** RenMori takes an
already-built Ren'Py 8.x distribution and produces a protected one: every asset —
scripts, sprites, CGs, audio, video, fonts, translations, and configuration — is
packed into an encrypted container and decrypted only inside the running engine.
Off-the-shelf unpackers and decompilers, and the agents that merely call them,
fail outright, and every build differs so no single tool works across games.

A game that runs on the player's machine can never be made uncrackable — the
engine must read its own assets, so the keys ship with it. RenMori does not claim
otherwise; it raises extraction from "run a tool" to dedicated, per-title,
per-version expert effort. The honest threat model is in
[docs/threat-model.md](docs/threat-model.md).

Chinese: [README.zh-CN.md](README.zh-CN.md).

---

## 1. Install & use the CLI

### Install

```bash
pip install renmori
renmori --version
```

Requires **Python 3.9+** on the developer's machine (reading a `renmori.toml`
config needs 3.11+, or `pip install tomli` on older versions). `cryptography` is
pulled in automatically. To work on the source instead:

```bash
git clone https://github.com/MewBaka/RenMori.git
cd RenMori && pip install -e .
```

### Protect a game

1. **Build your game** in the Ren'Py launcher (*Build Distributions*). RenMori
   runs on that output and never touches your source.
2. **Protect the build** — the input is the built folder, or the `.zip` the
   launcher made (it is unzipped for you):

   ```bash
   renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected
   # or straight from the archive:
   renmori protect ./dist/MyGame-1.0-pc.zip
   ```

   The first full protect downloads the closed plugin for your platform from the
   public release, verifies it, and caches it — no manual step. On a terminal it
   asks first; in CI it downloads automatically.

3. **Verify** the result (usable as a CI gate):

   ```bash
   renmori verify ./dist/MyGame-1.0-pc-protected
   ```

4. **Ship** the protected folder as your release (`renmori.rmc` + `renmori.rpe`
   together). Don't re-run the Ren'Py launcher on it — that rebuilds from source
   and drops the protection.

The command is zero-config by default, prints a machine-readable JSON result line
for CI, and has clear exit codes. An optional `renmori.toml` controls chunk size,
an exclude list, lockdown, strength, and key sources. For the open-source
**baseline** format (no plugin, fully offline), pass `--strength baseline`. Full
reference: [docs/usage.md](docs/usage.md) and
[examples/renmori.toml](examples/renmori.toml).

---

## 2. Documentation

> A hosted docs site is coming soon; until then the links below point at the
> sources in this repository. (Each page also has a `*.zh-CN.md` Chinese version.)

**Understand it**

- [research.md](docs/research.md) — what already exists and why a new tool is needed
- [architecture.md](docs/architecture.md) — the full design, layer by layer
- [threat-model.md](docs/threat-model.md) — what it stops, and what it cannot

**Protect your game**

- [usage.md](docs/usage.md) — the `renmori` CLI in full (`protect` / `verify`, flags, output)
- [examples/renmori.toml](examples/renmori.toml) — the configuration file

**Automate in CI**

- [ci.md](docs/ci.md) — CI pipelines and key management
- [examples/github-actions-protect.yml](examples/github-actions-protect.yml) — a sample GitHub Actions workflow
- [interface.md](docs/interface.md) — the contract between the open tool and the closed plugin

**Ship**

- [steam-release.md](docs/steam-release.md) — publishing to Steam (overlay, DRM, Steamworks)

---

## 3. Licensing

RenMori — the framework and tools, the closed plugin, and the runtime that ships
inside a game — is under the **RenMori License 1.0**:
[`LICENSE`](LICENSE) (Chinese: [`LICENSE.zh-CN.md`](LICENSE.zh-CN.md)).

- **Free to use.** Protecting any Ren'Py game, commercial or not, is free, and the
  RenMori runtime may be redistributed embedded in a released game at no charge.
- **No resale.** Selling RenMori itself or a modified version, or running a paid
  "encryption-as-a-service" with it, is not permitted.
- This is a **source-available** license, not an OSI open-source one, because the
  no-resale term cannot be expressed under a permissive license.

Third-party notices are in [`NOTICE`](NOTICE) (note the FFmpeg LGPL/GPL terms). No
warranty of unbreakability is given — see the license and
[docs/threat-model.md](docs/threat-model.md).

Full terms and FAQ: *(website coming soon)*.
