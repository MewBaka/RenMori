#!/usr/bin/env python3
"""
Performance benchmark: protected vs unprotected builds, measured inside a real
Ren'Py engine.

It copies a base game, adds a synthetic asset set sized like a commercial
visual novel (CG, sprites, UI, BGM, voice, video; random bytes, so as
incompressible as real encoded media), and produces three builds of it:
unprotected, baseline-protected and fully protected (the latter only when the
closed plugin is available). It then measures:

* build time: wall-clock time of `renmori protect` and the container's size
  overhead;
* in-engine reads: a benchmark extension injected into each build reads every
  asset through ``renpy.loader.load`` (the path the engine itself uses) and
  times it, plus open-to-first-64KB and random seek + 64KB read on the video;
* lint: wall-clock time of a full `renpy.sh <game> lint`, which loads and parses
  every script;
* container layer (host): sequential throughput and random 4KB read latency of
  the reference reader across chunk sizes.

Frame time during real play is NOT measured here.

Usage:
    python tools/benchmark.py --sdk /Applications/renpy-8.5.2-sdk \\
        --game /Applications/renpy-8.5.2-sdk/the_question --json bench.json

Exit code 0 = every build ran and every variant's reads completed.
"""

import argparse
import datetime
import json
import os
import pathlib
import platform
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from renmori import __version__  # noqa: E402

# Runs at extension-load time inside the engine, after renmori.rpe (if any) has
# installed its loader hook, so every read below goes through the same path the
# engine uses for real assets. Prints one JSON line and exits before startup.
BENCH_EXT = r'''
import os, sys, json, time, random, renpy

BLOCK = 1 << 20

def read_all(name):
    n = 0
    with renpy.loader.load(name) as f:
        while True:
            b = f.read(BLOCK)
            if not b:
                break
            n += len(b)
    return n

try:
    spec = json.load(open(os.environ["RENMORI_BENCH"]))
    result = {"categories": {}}

    for cat, names in spec["categories"].items():
        for name in names:
            read_all(name)
        times = []
        nbytes = 0
        for _ in range(spec["passes"]):
            nbytes = 0
            t0 = time.perf_counter()
            for name in names:
                nbytes += read_all(name)
            times.append(time.perf_counter() - t0)
        result["categories"][cat] = {"files": len(names), "bytes": nbytes, "times": times}

    big, size, samples = spec["seek_file"], spec["seek_size"], spec["seek_samples"]
    first = []
    for _ in range(samples):
        t0 = time.perf_counter()
        with renpy.loader.load(big) as f:
            f.read(65536)
        first.append(time.perf_counter() - t0)

    rng = random.Random(1234)
    seeks = []
    with renpy.loader.load(big) as f:
        for _ in range(samples):
            off = rng.randrange(0, size - 65536)
            t0 = time.perf_counter()
            f.seek(off)
            f.read(65536)
            seeks.append(time.perf_counter() - t0)

    result["open_first_64k"] = first
    result["seek_read_64k"] = seeks
    print("RENMORIBENCH " + json.dumps(result))
    sys.stdout.flush(); os._exit(0)
except Exception as e:
    print("RENMORIBENCH FATAL %r" % e); sys.stdout.flush(); os._exit(4)
'''

# category -> (extension, file size in bytes, file count) at --scale 1.0
PROFILE = {
    "cg":     (".png",   2 * 1024 * 1024,  40),
    "sprite": (".png",   600 * 1024,       60),
    "ui":     (".png",   24 * 1024,       400),
    "bgm":    (".ogg",   4 * 1024 * 1024,  10),
    "voice":  (".opus",  60 * 1024,       300),
    "video":  (".webm",  64 * 1024 * 1024,  2),
}

BENCH_DIR = "renmori_bench"
EXT_NAME = "zz_renmori_bench.rpe.py"
CHUNK_SIZES = (16 * 1024, 64 * 1024, 256 * 1024, 1024 * 1024)


def make_workload(game_dir, scale):
    """Write the synthetic asset set; return {category: [game-relative names]}."""
    rng = random.Random(20261031)
    out = game_dir / BENCH_DIR
    out.mkdir()
    cats = {}
    for cat, (ext, size, count) in PROFILE.items():
        count = max(1, int(round(count * scale)))
        names = []
        for i in range(count):
            name = "%s/%s_%03d%s" % (BENCH_DIR, cat, i, ext)
            (game_dir / name).write_bytes(rng.randbytes(size))
            names.append(name)
        cats[cat] = names
    return cats


def dir_bytes(path):
    return sum(p.stat().st_size for p in pathlib.Path(path).rglob("*") if p.is_file())


def median(xs):
    return statistics.median(xs)


def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]


def protect(src, out, strength):
    cmd = [sys.executable, "-m", "renmori", "protect", str(src), "-o", str(out),
           "-y", "--quiet", "--no-hints"]
    # Full protection is the default; the plugin names its own strength (e.g.
    # "poly"), so "full" is selected by passing no --strength at all.
    if strength != "full":
        cmd += ["--strength", strength]
    env = dict(os.environ, PYTHONPATH=str(SRC_DIR))
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    elapsed = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError("protect --strength %s failed (rc=%d): %s" % (
            strength, proc.returncode, proc.stderr.strip()[-500:]))
    return elapsed


def bench_build_time(src, work, strength, repeat):
    times = []
    for i in range(repeat):
        out = work / ("protect-%s-%d" % (strength, i))
        times.append(protect(src, out, strength))
        if i < repeat - 1:
            shutil.rmtree(out)
    final = work / ("protect-%s-%d" % (strength, repeat - 1))
    manifest = json.loads((final / "renmori-manifest.json").read_text())
    return final, times, manifest


def run_renpy(sdk, game, args, env=None):
    t0 = time.perf_counter()
    proc = subprocess.run(["/bin/bash", str(sdk / "renpy.sh"), str(game)] + args,
                          cwd=sdk, env=env or dict(os.environ), capture_output=True, text=True)
    return proc, time.perf_counter() - t0


def bench_in_engine(sdk, build, spec_path):
    ext = build / "game" / EXT_NAME
    ext.write_text(BENCH_EXT)
    try:
        env = dict(os.environ, RENMORI_BENCH=str(spec_path))
        proc, _ = run_renpy(sdk, build, ["lint"], env)
    finally:
        ext.unlink()
    for line in proc.stdout.splitlines():
        if line.startswith("RENMORIBENCH "):
            payload = line[len("RENMORIBENCH "):]
            if payload.startswith("FATAL"):
                raise RuntimeError("in-engine benchmark failed in %s: %s" % (build.name, payload))
            return json.loads(payload)
    raise RuntimeError("no benchmark output from %s\n%s" % (build.name, proc.stderr[-2000:]))


def bench_lint(sdk, build, repeat):
    times = []
    for _ in range(repeat):
        proc, elapsed = run_renpy(sdk, build, ["lint"])
        blob = proc.stdout + proc.stderr
        if "Traceback (most recent call last)" in blob:
            raise RuntimeError("lint failed in %s:\n%s" % (build.name, blob[-2000:]))
        times.append(elapsed)
    return times


def bench_container(work, size_mb, samples):
    """Reference reader on the host: throughput and random-read latency per chunk size."""
    from renmori.container import ContainerReader, ContainerWriter

    key = os.urandom(32)
    data = random.Random(7).randbytes(size_mb * 1024 * 1024)
    rows = []
    for chunk in CHUNK_SIZES:
        path = work / ("chunk-%d.rmc" % chunk)
        with ContainerWriter(str(path), key, chunk_size=chunk) as w:
            w.add_bytes("blob.bin", data)
        reader = ContainerReader(str(path), key)

        seq = []
        for _ in range(3):
            t0 = time.perf_counter()
            with reader.open_stream("blob.bin") as s:
                while s.read(1 << 20):
                    pass
            seq.append(time.perf_counter() - t0)

        rng = random.Random(99)
        lat = []
        with reader.open_stream("blob.bin") as s:
            for _ in range(samples):
                off = rng.randrange(0, len(data) - 4096)
                t0 = time.perf_counter()
                s.seek(off)
                s.read(4096)
                lat.append(time.perf_counter() - t0)

        rows.append({
            "chunk_size": chunk,
            "backend": reader.backend.name,
            "seq_mb_s": size_mb / median(seq),
            "rand4k_ms_median": median(lat) * 1000,
            "rand4k_ms_p95": p95(lat) * 1000,
            "size_overhead_pct": (path.stat().st_size - len(data)) / len(data) * 100,
        })
        path.unlink()
    return rows


def environment(sdk):
    renpy_version = "unknown"
    vc = sdk / "renpy" / "vc_version.py"
    if vc.exists():
        ns = {}
        exec(vc.read_text(), ns)
        renpy_version = ns.get("version", renpy_version)
    cpu = platform.processor() or platform.machine()
    mem = None
    if sys.platform == "darwin":
        cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                             capture_output=True, text=True).stdout.strip() or cpu
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout
        mem = int(out) if out.strip().isdigit() else None
    elif hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
        mem = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return {
        "date": datetime.date.today().isoformat(),
        "os": platform.platform(),
        "cpu": cpu,
        "memory_gb": round(mem / 2 ** 30) if mem else None,
        "python": platform.python_version(),
        "renpy": renpy_version,
        "renmori": __version__,
    }


def summarize(results):
    """Per-variant MB/s and ms-per-file for each category, plus ratios to unprotected."""
    summary = {}
    for variant, r in results["engine"].items():
        cats = {}
        for cat, c in r["categories"].items():
            t = median(c["times"])
            cats[cat] = {
                "files": c["files"],
                "mb": c["bytes"] / 2 ** 20,
                "mb_s": c["bytes"] / 2 ** 20 / t,
                "ms_per_file": t / c["files"] * 1000,
            }
        summary[variant] = {
            "categories": cats,
            "open_first_64k_ms": median(r["open_first_64k"]) * 1000,
            "seek_read_64k_ms": median(r["seek_read_64k"]) * 1000,
            "seek_read_64k_ms_p95": p95(r["seek_read_64k"]) * 1000,
        }
    return summary


def print_report(results):
    env = results["environment"]
    print("\n# RenMori benchmark\n")
    print("%s | %s | %s GB | Python %s | Ren'Py %s | RenMori %s\n" % (
        env["os"], env["cpu"], env["memory_gb"], env["python"], env["renpy"], env["renmori"]))

    print("## Build time (renmori protect)\n")
    print("| strength | game/ MB | median s | MB/s | container overhead |")
    print("|---|---:|---:|---:|---:|")
    for strength, b in results["build"].items():
        t = median(b["times"])
        print("| %s | %.1f | %.2f | %.1f | %.3f%% |" % (
            strength, b["input_mb"], t, b["input_mb"] / t, b["overhead_pct"]))

    summary = results["summary"]
    variants = list(summary)
    print("\n## In-engine reads via renpy.loader.load (MB/s, median of passes)\n")
    print("| category | files | MB | " + " | ".join(variants) + " |")
    print("|---|---:|---:|" + "---:|" * len(variants))
    for cat in summary[variants[0]]["categories"]:
        c0 = summary[variants[0]]["categories"][cat]
        cells = ["%.0f" % summary[v]["categories"][cat]["mb_s"] for v in variants]
        print("| %s | %d | %.1f | %s |" % (cat, c0["files"], c0["mb"], " | ".join(cells)))

    print("\n## In-engine latency (ms, median)\n")
    print("| measurement | " + " | ".join(variants) + " |")
    print("|---|" + "---:|" * len(variants))
    for key, label in (("open_first_64k_ms", "open + first 64KB of video"),
                       ("seek_read_64k_ms", "random seek + 64KB read in video")):
        print("| %s | %s |" % (label, " | ".join("%.3f" % summary[v][key] for v in variants)))

    print("\n## lint (loads and parses every script; s, median)\n")
    print("| " + " | ".join(variants) + " |")
    print("|" + "---:|" * len(variants))
    print("| " + " | ".join("%.2f" % median(results["lint"][v]) for v in variants) + " |")

    print("\n## Container layer, host reference reader\n")
    print("| chunk | backend | sequential MB/s | random 4KB median ms | p95 ms | size overhead |")
    print("|---:|---|---:|---:|---:|---:|")
    for r in results["container"]:
        print("| %d KB | %s | %.0f | %.3f | %.3f | %.3f%% |" % (
            r["chunk_size"] // 1024, r["backend"], r["seq_mb_s"],
            r["rand4k_ms_median"], r["rand4k_ms_p95"], r["size_overhead_pct"]))
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sdk", required=True, help="Ren'Py SDK dir (has renpy.sh)")
    ap.add_argument("--game", required=True, help="base game dir (has game/), e.g. the SDK's the_question")
    ap.add_argument("--scale", type=float, default=1.0, help="workload size multiplier (default 1.0, about 310 MB)")
    ap.add_argument("--passes", type=int, default=5, help="timed read passes per category in-engine")
    ap.add_argument("--repeat", type=int, default=3, help="repetitions for protect and lint timings")
    ap.add_argument("--strength", choices=("both", "baseline", "full"), default="both",
                    help="which protected variants to build (default: both; full needs the plugin)")
    ap.add_argument("--json", help="write the raw and summarized results here")
    ap.add_argument("--work", help="work directory (default: a temp dir, removed afterwards)")
    ap.add_argument("--keep", action="store_true", help="keep the work directory")
    args = ap.parse_args()

    sdk = pathlib.Path(args.sdk).resolve()
    if not (sdk / "renpy.sh").exists():
        print("no renpy.sh at %s" % sdk, file=sys.stderr)
        return 2

    work = pathlib.Path(args.work or tempfile.mkdtemp(prefix="renmori-bench-")).resolve()
    work.mkdir(parents=True, exist_ok=True)
    try:
        src = work / "unprotected"
        shutil.copytree(args.game, src, ignore=shutil.ignore_patterns("saves", "cache", "renmori*"))
        cats = make_workload(src / "game", args.scale)
        video = cats["video"][0]
        spec = {
            "categories": cats,
            "passes": args.passes,
            "seek_file": video,
            "seek_size": (src / "game" / video).stat().st_size,
            "seek_samples": 200,
        }
        spec_path = work / "spec.json"
        spec_path.write_text(json.dumps(spec))
        input_mb = dir_bytes(src / "game") / 2 ** 20
        print("workload: %.1f MB in game/ (%d synthetic files)" % (
            input_mb, sum(len(v) for v in cats.values())), file=sys.stderr)

        strengths = ["baseline", "full"] if args.strength == "both" else [args.strength]
        results = {"environment": environment(sdk), "workload": {
            "scale": args.scale, "input_mb": input_mb,
            "profile": {k: {"ext": e, "bytes": s, "count": len(cats[k])} for k, (e, s, _) in PROFILE.items()},
        }, "build": {}, "engine": {}, "lint": {}}

        builds = {"unprotected": src}
        for strength in strengths:
            print("protect --strength %s ×%d" % (strength, args.repeat), file=sys.stderr)
            out, times, manifest = bench_build_time(src, work, strength, args.repeat)
            container = dir_bytes(out / "game") / 2 ** 20
            results["build"][strength] = {
                "times": times, "input_mb": input_mb, "output_game_mb": container,
                "overhead_pct": (container - input_mb) / input_mb * 100,
                "manifest_strength": manifest.get("strength"),
            }
            builds[strength] = out

        for variant, build in builds.items():
            print("in-engine reads: %s" % variant, file=sys.stderr)
            results["engine"][variant] = bench_in_engine(sdk, build, spec_path)
            print("lint ×%d: %s" % (args.repeat, variant), file=sys.stderr)
            results["lint"][variant] = bench_lint(sdk, build, args.repeat)

        print("container layer (host)", file=sys.stderr)
        results["container"] = bench_container(work, 64, 1000)
        results["summary"] = summarize(results)

        print_report(results)
        if args.json:
            pathlib.Path(args.json).write_text(json.dumps(results, indent=2) + "\n")
            print("wrote %s" % args.json, file=sys.stderr)
        return 0
    finally:
        if args.keep:
            print("kept %s" % work, file=sys.stderr)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
