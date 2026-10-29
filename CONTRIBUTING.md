# Contributing to renmori

Thanks for your interest. renmori is an **open-core** project: the framework in
this repository is open source, and a separate closed-source binary plugin
provides the polymorphism engine, key-derivation logic, and anti-tamper runtime.
This document covers contributions to the **open** parts.

## Contributor License Agreement (CLA) — required

Because renmori has a commercial, closed-source component built partly on this
open codebase, **every contributor must agree to a CLA before their contribution
can be merged.** The CLA grants the project the rights to:

- use the contribution in the open-source distribution, and
- use it in the closed-source commercial build, and
- relicense the open parts if the project's open license changes (e.g. the
  pending MIT → Apache-2.0 decision).

Without a CLA we cannot accept code, because we could not lawfully use it in the
commercial build. The CLA process (individual and corporate) will be linked here
once finalized. Until then, please open an issue to discuss before writing code,
so no one contributes work that can't yet be accepted.

## Scope: what belongs in the open repo

**In scope (open):**

- The CLI, config parsing, exit-code/CI behavior, GitHub Actions samples.
- The `renpy.loader` hook framework / runtime SDK.
- The baseline container format (v1) and its reader/writer.
- Standard crypto primitive *usage* (the algorithms themselves are public).
- Docs, samples, tests, compatibility fixes across Ren'Py 8.x versions.

**Out of scope (closed — do not submit, and please don't reverse it):**

- The per-build polymorphism / mutation engine.
- Key-derivation obfuscation and key-recovery logic.
- Native anti-tamper internals.

If a change needs to touch the process interface between the open CLI and the
closed binary, propose an interface change in an issue first — the interface is
open and versioned, but both sides must stay compatible.

## Security principles every contribution must respect

These are hard rules, not preferences:

1. **Performance wins.** No measure that regresses runtime performance (frame
   time, scene transitions, CG/video) lands. Nothing anti-debug or
   self-checking on the hot path.
2. **No plaintext on disk**, ever — fonts included.
3. **Decrypt data only; never generate or execute decrypted code at runtime**
   (this keeps macOS entitlement-free; see
   [docs/architecture.md](docs/architecture.md)).
4. **No telemetry / no phone-home.** The loader framework is open precisely so
   people can verify this. Don't add network calls.
5. **Honesty about protection.** Don't add claims, in code comments, docs, or
   messages, that exceed what [docs/threat-model.md](docs/threat-model.md)
   allows. No "uncrackable".

## Development workflow

1. Open an issue describing the change (and, for now, confirm CLA willingness).
2. Branch from `main`.
3. Keep changes focused; include tests where the open code is testable.
4. Make sure the sample protect-and-run flow still passes and performance is
   unchanged.
5. Open a PR referencing the issue.

## Reporting security issues

Please **do not** open a public issue for a vulnerability in the protection
scheme. A private disclosure channel will be listed here; until then, contact
the maintainer directly. Note that the threat model already documents what is
*not* protected (screen/memory capture, dedicated per-game reversing) — those
are known limits, not vulnerabilities.
