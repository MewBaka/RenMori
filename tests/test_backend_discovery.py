import os

from renmori.container.crypto import runtime_lib_candidates


def test_finds_librenpython_beside_executable(tmp_path):
    # Simulate the lib dir next to Ren'Py's python executable on each platform.
    for name in ("librenpython.dylib", "librenpython.so", "librenpython.dll"):
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "python").write_bytes(b"")  # not a lib, must be ignored

    found = runtime_lib_candidates(str(tmp_path))
    bases = {os.path.basename(p) for p in found}
    assert bases == {"librenpython.dylib", "librenpython.so", "librenpython.dll"}


def test_empty_when_absent(tmp_path):
    assert runtime_lib_candidates(str(tmp_path)) == []
