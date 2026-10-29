#!/usr/bin/env python3
"""
End-to-end verification that a protected game decrypts correctly *inside* a real
Ren'Py engine.

It copies a game, protects it with the renmori CLI, injects a checker extension
that opens representative assets through ``renpy.loader.load`` and compares each
to the original's SHA-256, runs the SDK, and asserts every file matched
byte-for-byte. It also confirms no plaintext Ren'Py files remain on disk.

Usage:
    python tools/verify_in_renpy.py --sdk /Applications/renpy-8.5.2-sdk \\
        --game /Applications/renpy-8.5.2-sdk/the_question

Exit code 0 = all representative assets decrypted byte-perfectly.
"""

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

# Runs at extension-load time (before the engine finishes starting), so it only
# checks things that don't need full engine state: non-script assets must
# decrypt byte-identically, and each script's stored payload must be transformed
# (not a standard pickle) yet reverse to a valid pickle via our patched loads.
# End-to-end script *parsing* is proven separately by a full `lint` run.
CHECKER = r'''
import os, sys, json, hashlib, struct, zlib, renpy

RPYC2 = b"RENPY RPC2"

def slot1(raw):
    assert raw[:len(RPYC2)] == RPYC2, "not an RPYC2 file"
    pos = len(RPYC2)
    while True:
        sid, start, length = struct.unpack("III", raw[pos:pos+12])
        if sid == 0:
            raise RuntimeError("no slot 1")
        if sid == 1:
            return zlib.decompress(raw[start:start+length])
        pos += 12

try:
    spec = json.load(open(os.environ["RENMORI_CHECK"]))
    allok = True

    for name, want in spec["assets"].items():
        try:
            h = hashlib.sha256(); total = 0
            with renpy.loader.load(name) as f:
                for b in iter(lambda: f.read(1 << 20), b""):
                    h.update(b); total += len(b)
            ok = (h.hexdigest() == want)
            print("RENMORICHK %s asset %s len=%d" % ("PASS" if ok else "FAIL", name, total))
            allok = allok and ok
        except Exception as e:
            print("RENMORICHK ERROR asset %s %r" % (name, e)); allok = False

    # The patched renpy.script.loads reverses our transform; feeding it the
    # stored (transformed) payload must yield a standard pickle (0x80...), the
    # exact input Ren'Py's real unpickler then consumes. We stop before the
    # unpickle itself, which needs engine state not ready at this phase.
    import renpy.script as S
    real_unpickler_loads = S.loads.__wrapped__ if hasattr(S.loads, "__wrapped__") else None
    for name in spec["scripts"]:
        try:
            with renpy.loader.load(name) as f:
                payload = slot1(f.read())
            transformed = payload[:1] != b"\x80"
            # Reverse the renmori layer exactly as the hook does, via a captured
            # reverse hook the extension exposes for verification.
            reverse = getattr(renpy.config, "_renmori_reverse_script", None)
            reversed_ok = False
            if reverse is not None:
                reversed_ok = reverse(payload)[:1] == b"\x80"
            print("RENMORICHK %s script %s transformed=%s reverses_to_pickle=%s" % (
                "PASS" if (transformed and reversed_ok) else "FAIL", name, transformed, reversed_ok))
            allok = allok and transformed and reversed_ok
        except Exception as e:
            print("RENMORICHK ERROR script %s %r" % (name, e)); allok = False

    # Injection block: a script planted on disk in the game dir (an un.rpyc-style
    # decompiler) must be refused, while a real container script still opens.
    inject = os.environ.get("RENMORI_INJECT")
    if inject:
        refused = renpy.loader.load_core(inject) is None
        good = spec["scripts"][0] if spec["scripts"] else None
        container_ok = (good is not None) and (renpy.loader.load_core(good) is not None)
        print("RENMORICHK %s inject refused=%s container_script_loads=%s" % (
            "PASS" if (refused and container_ok) else "FAIL", refused, container_ok))
        allok = allok and refused and container_ok

    print("RENMORICHK RESULT", "ALLPASS" if allok else "FAILED")
    sys.stdout.flush(); os._exit(0 if allok else 3)
except Exception as e:
    print("RENMORICHK FATAL %r" % e); sys.stdout.flush(); os._exit(4)
'''

# One file per asset type we care about; only those present are checked.
ASSET_QUOTA = {
    ".ttf": 2, ".otf": 2, ".png": 1, ".jpg": 1, ".webp": 1,
    ".opus": 1, ".ogg": 1, ".webm": 1, ".avi": 1, ".ogv": 1,
}
SCRIPT_EXTS = (".rpyc", ".rpymc")


def pick_representatives(game_dir):
    """Return (assets {name: sha256}, scripts [name])."""
    game_dir = pathlib.Path(game_dir)
    assets = {}
    scripts = []
    quota = dict(ASSET_QUOTA)
    for p in sorted(game_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(game_dir)
        if rel.parts[0] in ("saves", "cache"):
            continue
        name = str(rel).replace(os.sep, "/")
        ext = p.suffix.lower()
        if ext in SCRIPT_EXTS and len(scripts) < 3:
            scripts.append(name)
        elif quota.get(ext, 0) > 0:
            assets[name] = _sha256(p)
            quota[ext] -= 1
    return assets, scripts


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdk", required=True, help="Ren'Py SDK dir (has renpy.sh)")
    ap.add_argument("--game", required=True, help="built game dir (has game/)")
    ap.add_argument("--keep", action="store_true", help="keep the temp dir")
    args = ap.parse_args()

    renpy_sh = pathlib.Path(args.sdk) / "renpy.sh"
    if not renpy_sh.exists():
        print("no renpy.sh at %s" % renpy_sh, file=sys.stderr)
        return 2

    work = pathlib.Path(tempfile.mkdtemp(prefix="renmori-verify-"))
    try:
        src = work / "src"
        shutil.copytree(args.game, src)

        assets, scripts = pick_representatives(src / "game")
        if not assets and not scripts:
            print("no representative files found under game/", file=sys.stderr)
            return 2
        print("checking %d assets + %d scripts: %s" % (
            len(assets), len(scripts), ", ".join(list(assets) + scripts)))

        protected = work / "protected"
        rc = subprocess.call([sys.executable, "-m", "renmori", "protect", str(src), "-o", str(protected)])
        if rc != 0:
            print("protect failed rc=%d" % rc, file=sys.stderr)
            return rc

        # No plaintext Ren'Py files should remain on disk.
        leftovers = [
            str(p) for p in (protected / "game").rglob("*")
            if p.suffix in (".rpa", ".rpyc", ".rpy", ".rpyb") and "cache" not in p.parts
        ]
        if leftovers:
            print("FAIL: plaintext files remain on disk: %s" % leftovers[:5], file=sys.stderr)
            return 1

        # Phase 1: early-load checks (assets byte-identical; scripts transformed
        # and reversible). The checker extension exits before the engine finishes.
        exp_path = work / "expected.json"
        exp_path.write_text(json.dumps({"assets": assets, "scripts": scripts}))
        checker = protected / "game" / "zz_renmori_check.rpe.py"
        checker.write_text(CHECKER)

        # Plant an un.rpyc-style decompiler on disk to prove it is refused.
        inject_name = "zz_injected.rpyc"
        (protected / "game" / inject_name).write_bytes(b"RENPY RPC2" + b"\x00" * 64)

        env = dict(os.environ, RENMORI_CHECK=str(exp_path), RENMORI_VERIFY="1", RENMORI_INJECT=inject_name)
        out = subprocess.run(
            ["/bin/bash", str(renpy_sh), str(protected), "lint"],
            cwd=args.sdk, env=env, capture_output=True, text=True,
        )
        for l in out.stdout.splitlines():
            if "RENMORICHK" in l:
                print(l)
        if "RENMORICHK RESULT ALLPASS" not in out.stdout:
            print("\nFAIL (phase 1).\n--- stderr tail ---\n%s" % out.stderr[-2000:], file=sys.stderr)
            return 1

        # Phase 2: a full lint with no checker (and no planted file), so the
        # engine actually loads and parses every (transformed) script. Proves
        # the script layer end-to-end.
        checker.unlink()
        (protected / "game" / inject_name).unlink()
        out2 = subprocess.run(
            ["/bin/bash", str(renpy_sh), str(protected), "lint"],
            cwd=args.sdk, env=dict(os.environ), capture_output=True, text=True,
        )
        blob = out2.stdout + out2.stderr
        errors = [m for m in ("Failed to load", "Could not load", "Traceback (most recent call last)") if m in blob]
        completed = "Lint is not a substitute" in blob or "The game contains" in blob
        if errors or not completed:
            print("\nFAIL (phase 2): script parsing in-engine.", file=sys.stderr)
            print("markers=%r completed=%s" % (errors, completed), file=sys.stderr)
            print(blob[-2000:], file=sys.stderr)
            return 1

        print("\nOK: assets byte-perfect; scripts transformed, reversible, and parsed end-to-end by lint.")
        return 0
    finally:
        if args.keep:
            print("kept %s" % work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
