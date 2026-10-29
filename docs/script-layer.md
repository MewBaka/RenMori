# Script layer & engine lockdown (M2)

M1 already encrypts every `.rpyc` inside the container, so off-the-shelf tools
can't reach them on a shipped build. M2 is **defense in depth** for the script
*source*, for the case where container contents are exposed (a leaked/derived
container key, or a memory dump), plus **engine hardening** that blocks injected
decompilers and locks down a release.

## 1. Script transform (baseline)

Compiled scripts carry their AST as a pickle in the RPYC2 slot payload
(`zlib(pickle((data, stmts)))`). At build time renmori replaces each pickle
payload with:

```
SCRIPT_MAGIC (b"RMSC\x01") || nonce(12) || AES-256-GCM(script_key, pickle)
```

- **`script_key` is independent of the container master key.** Exposing the
  container's contents with the master key alone does *not* yield decompilable
  scripts — you also need the script key, which lives in the runtime extension
  (and, in production, in the closed native runtime).
- Reversible and lossless: the runtime decrypts back to the exact original
  pickle before Ren'Py unpickles, so AST semantics are untouched. Implemented in
  [`script/transform.py`](../src/renmori/script/transform.py) (build) and the
  `renpy.script.loads` patch in [`runtime/hook.py`](../src/renmori/runtime/hook.py)
  (runtime).

### Why this defeats the decompilers

The stored slot payload is no longer a pickle, so a decompiler that extracts it
sees `SCRIPT_MAGIC || ciphertext`. Verified against the two named tools on the
same `script.rpyc`:

| Tool | Original `.rpyc` | renmori-transformed |
|------|------------------|---------------------|
| `unrpyc` | decompiles to `.rpy` | **fails** |
| `unrpyc --try-harder` | — | **fails** (its zlib/base64/hex/escape layers can't touch AES-GCM) |
| `rpycdec` | decompiles to `.rpy` | **fails** (`Unsupported file format`) |

### Closed upgrade: per-build AST structural randomization

The baseline's reversal is one keyed step; an attacker who recovers the script
key for one build gets standard pickle back. The closed polymorphism engine goes
further: it randomizes the compiled script's *structure* per build so that, even
fully decrypted, the payload carries no standard class names a decompiler can
dispatch on, and no single reversible key recovers it. It is a build-time
transform that never ships to players, and it differs per build so a break does
not port. Mechanism and implementation are proprietary — see the private
`MewBaka/RenMori-core` repository.

## 2. Injection block (engine layer)

`un.rpyc`-style decompilers work by being dropped into `game/` and loaded as a
script, whose init code dumps everything. renmori refuses to **open** any
script-like file (`.rpyc/.rpymc/.rpy/.rpym/.rpe`) that physically resolves
inside the game directory, so an injected file's code never runs. Engine scripts
under `renpy/common` are unaffected (the guard is scoped to the game dir).
Legitimate scripts come only from the container. Verified: a planted
`game/*.rpyc` returns `None` from `load_core` while container scripts still load.

## 3. Release lockdown

In a protected build the runtime sets `config.developer = False` and
`config.console = False`, and refuses data-exporting subcommands (`compile`,
`dialogue`, `translate`, `add_from`, `merge_strings`). `renpy.sh … lint`/`run`
still work.

## Verification

```bash
python tools/verify_in_renpy.py --sdk /Applications/renpy-8.5.2-sdk \
    --game /Applications/renpy-8.5.2-sdk/the_question
```

Phase 1 (extension load): assets byte-identical; each script payload is
transformed (not pickle) and reverses to a valid pickle; a planted on-disk
script is refused. Phase 2 (full `lint`): the engine loads and parses every
transformed script end-to-end with no errors. Plus unit tests
[`tests/test_script.py`](../tests/test_script.py) for lossless transform
round-trip.
