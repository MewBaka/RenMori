"""
The renmori runtime hook. Copied into the ``renmori_rt`` package inside
``game/renmori.rpe`` by the build tool and invoked from that zip's
``autorun.py`` before Ren'Py indexes files.

Responsibilities:
  * install a file-open callback at the front of ``renpy.loader.file_open_callbacks``
    so container entries are served (decrypted) ahead of anything on disk;
  * register a scandir callback so discovery (``listdirfiles``), ``loadable``,
    and the case-insensitive ``lower_map`` all know about container entries;
  * keep small/medium files on Ren'Py's fastest C path and stream large ones.

Stdlib + ctypes only (see docs/loader-hook.md). The master-key handling here is
the BASELINE placeholder; the shipping closed runtime replaces it.
"""

import os

# Files at or below this size are decrypted fully and handed to Ren'Py as a C
# buffer (no GIL on subsequent reads). Larger files stream chunk-by-chunk.
STREAM_THRESHOLD = 4 * 1024 * 1024

# Script-like extensions that must only ever come from the container. Any copy
# on disk (e.g. an injected un.rpyc decompiler) is refused.
_SCRIPT_EXTS = (".rpyc", ".rpymc", ".rpy", ".rpym", ".rpe", ".rpe.py")

# Command-line subcommands that export game data; refused in a protected build.
_BLOCKED_COMMANDS = {"compile", "dialogue", "translate", "add_from", "merge_strings"}

_installed = False


def install(container_path, master_key, script_key=None, lockdown=True):
    global _installed
    if _installed:
        return

    import renpy

    from .reader import ContainerReader

    if not os.path.exists(container_path):
        renpy_log("renmori: container not found at %s" % container_path)
        return

    backend = _runtime_backend()
    reader = ContainerReader(container_path, master_key, backend=backend)

    # Ren'Py 8.4+ exposes pygame_sdl2 as `renpy.pygame`; 8.0–8.3 still import it
    # as the top-level `pygame_sdl2`. Support both so the hook works across the
    # whole 8.x range (on 8.0–8.3 the renpy.pygame-only import crashed at boot).
    try:
        from renpy.pygame.rwobject import RWopsIO
    except ImportError:
        from pygame_sdl2.rwobject import RWopsIO

    def open_callback(name):
        if name not in reader:
            return None
        try:
            if reader.size(name) <= STREAM_THRESHOLD:
                return RWopsIO.from_buffer(reader.read_bytes(name), name=name)
            return RWopsIO(reader.open_stream(name), name=name)
        except Exception as e:  # noqa: BLE001 - never hard-crash the loader
            renpy_log("renmori: failed to open %r: %s" % (name, e))
            return None

    # Front of the chain: container wins over any stray plaintext on disk.
    renpy.loader.file_open_callbacks.insert(0, open_callback)

    def scandir_callback(add, seen):
        for n in reader.names():
            add(None, n, renpy.loader.game_files, seen)

    renpy.loader.scandirfiles_callbacks.insert(0, scandir_callback)

    _install_injection_guard(renpy)
    _install_exists_fallback(renpy, reader)

    if script_key is not None:
        _install_script_protection(renpy, backend, script_key)

    if lockdown:
        _install_lockdown(renpy)

    _installed = True
    renpy_log("renmori: serving %d entries from %s" % (len(reader.names()), os.path.basename(container_path)))


def _install_injection_guard(renpy):
    """
    Serve scripts only from the container: refuse to open any script-like file
    that lives on disk. This neutralizes injected decompilers (e.g. un.rpyc /
    bytecode.rpyb dropped into game/), whose code only runs if Ren'Py can open
    and load them.
    """
    loader = renpy.loader
    orig_fs = loader.load_from_filesystem

    gamedir = os.path.abspath(renpy.config.gamedir)

    def under_gamedir(name):
        # Refuse a script only if it physically resolves inside the game dir
        # (an injection point). Engine scripts under renpy/common must still load.
        try:
            path = loader.transpath(name)
        except Exception:  # noqa: BLE001
            return False
        if not path:
            return False
        return os.path.abspath(path).startswith(gamedir + os.sep)

    def filesystem_guard(name):
        if name.lower().endswith(_SCRIPT_EXTS) and under_gamedir(name):
            renpy_log("renmori: refused on-disk script %r" % name)
            return None
        return orig_fs(name)

    for i, cb in enumerate(loader.file_open_callbacks):
        if cb is orig_fs:
            loader.file_open_callbacks[i] = filesystem_guard
            break


def _install_exists_fallback(renpy, reader):
    """`renpy.exists()` checks disk only (via transfn); make it also see files
    that now live in the container."""
    orig = getattr(renpy, "exists", None)
    if orig is None:
        return

    def exists(fn):
        try:
            if orig(fn):
                return True
        except Exception:  # noqa: BLE001
            pass
        return fn in reader

    renpy.exists = exists


def _install_script_protection(renpy, backend, script_key):
    """Reverse the script transform just before Ren'Py unpickles, so disk/memory
    exposure of the container does not yield standard decompilable .rpyc."""
    from .format import SCRIPT_MAGIC

    import renpy.script as script_mod

    real_loads = script_mod.loads
    magic_len = len(SCRIPT_MAGIC)

    def reverse(s):
        """Undo the renmori script transform; return a standard pickle."""
        if s[:magic_len] == SCRIPT_MAGIC:
            nonce = s[magic_len : magic_len + 12]
            ct = s[magic_len + 12 :]
            return backend.decrypt(script_key, nonce, ct, b"")
        return s

    def script_loads(s):
        return real_loads(reverse(s))

    script_mod.loads = script_loads

    # Verification-only affordance (never exposed in a normal build): lets the
    # test harness confirm the transform reverses to a valid pickle at a phase
    # where full unpickling isn't yet possible.
    if os.environ.get("RENMORI_VERIFY"):
        renpy.config._renmori_reverse_script = reverse


def _install_lockdown(renpy):
    """Disable developer affordances and data-export subcommands in a release."""
    try:
        renpy.config.developer = False
        renpy.config.console = False
    except Exception:  # noqa: BLE001
        pass

    try:
        command = getattr(renpy.game.args, "command", None)
        if command in _BLOCKED_COMMANDS:
            renpy_log("renmori: refusing command %r in a protected build" % command)
            raise SystemExit(2)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        pass


def _runtime_backend():
    """
    Pick an AES-GCM backend that actually works inside Ren'Py's bundled Python,
    which has no pip packages and whose only correctly-built OpenSSL is the one
    exported by librenpython (right next to the python executable). On Windows
    we use the OS's CNG instead.
    """
    import sys

    from .crypto import CNGBackend, OpenSSLBackend, runtime_lib_candidates, select_backend

    if sys.platform == "win32":
        try:
            return CNGBackend()
        except Exception as e:  # noqa: BLE001
            renpy_log("renmori: CNG backend unavailable (%s), falling back" % e)
            return select_backend()

    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    for cand in runtime_lib_candidates(exe_dir):
        try:
            return OpenSSLBackend(lib=cand)
        except Exception as e:  # noqa: BLE001
            renpy_log("renmori: %s not usable (%s)" % (os.path.basename(cand), e))

    return select_backend()


def renpy_log(msg):
    try:
        import renpy

        renpy.display.log.write("%s", msg)
    except Exception:
        print(msg)
