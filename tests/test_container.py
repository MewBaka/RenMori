import glob
import os

import pytest

from renmori.container import ContainerReader, ContainerWriter
from renmori.container.crypto import (
    CryptographyBackend,
    DecryptError,
    OpenSSLBackend,
    select_backend,
)

KEY = bytes(range(32))


def _renpy_libcrypto():
    """Locate a Ren'Py runtime library that exports OpenSSL EVP symbols, so the
    real runtime decrypt path is exercised on this host. Returns None if no SDK
    is installed."""

    pats = [
        "/Applications/renpy-*/lib/py3-*/librenpython.dylib",
        os.path.expanduser("~/Applications/renpy-*/lib/py3-*/librenpython.dylib"),
        "/Applications/renpy-*/lib/py3-*/librenpython.so",
    ]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def _openssl_backend():
    """OpenSSL backend bound to a usable libcrypto, or None if unavailable."""
    lib = _renpy_libcrypto()
    try:
        return OpenSSLBackend(lib=lib) if lib else OpenSSLBackend()
    except OSError:
        return None


def _backends():
    backends = [CryptographyBackend()]
    ob = _openssl_backend()
    if ob is not None:
        backends.append(ob)
    return backends


def _pack(tmp_path, entries, chunk_size=64 * 1024):
    path = str(tmp_path / "test.rmc")
    with ContainerWriter(path, KEY, chunk_size=chunk_size) as w:
        for name, data in entries.items():
            w.add_bytes(name, data)
    return path


def test_no_gcm_nonce_reuse(tmp_path):
    # Catastrophic-failure guard: AES-GCM must never reuse a (key, nonce). Pack
    # many files — including identical content and identical sizes — then recompute
    # every (file_key, chunk_nonce) pair from the index and assert all are unique.
    # This would catch a regression that made file_id deterministic/constant or
    # dropped the chunk index from the nonce.
    from renmori.container import format as fmt

    entries = {}
    for i in range(60):
        entries["dup/%d.bin" % i] = b"identical content block" * 9000   # same bytes
        entries["rnd/%d.bin" % i] = os.urandom(64 * 1024 * 3 + 7)       # multi-chunk
    path = _pack(tmp_path, entries, chunk_size=64 * 1024)
    r = ContainerReader(path, KEY)

    seen = set()
    for name, (offset, size, file_id) in r._files.items():
        key = fmt.file_key(KEY, r.header.container_id, file_id)
        for i in range(fmt.chunk_count(size, r.header.chunk_size)):
            pair = (key, fmt.chunk_nonce(file_id, i))
            assert pair not in seen, "GCM nonce reuse at %s chunk %d" % (name, i)
            seen.add(pair)
    # every file got a distinct file_id — the randomness that makes keys per-file
    ids = [fid for _, _, fid in r._files.values()]
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("backend", _backends(), ids=lambda b: b.name)
def test_round_trip(tmp_path, backend):
    entries = {
        "empty.txt": b"",
        "small.txt": b"hello renmori",
        "exact.bin": os.urandom(64 * 1024),           # exactly one chunk
        "multi.bin": os.urandom(64 * 1024 * 2 + 123),  # several chunks + remainder
        "images/bg.png": os.urandom(5000),
    }
    path = _pack(tmp_path, entries)
    r = ContainerReader(path, KEY, backend=backend)

    assert set(r.names()) == set(entries)
    for name, data in entries.items():
        assert r.read_bytes(name) == data, name
        assert r.size(name) == len(data)


@pytest.mark.parametrize("backend", _backends(), ids=lambda b: b.name)
def test_stream_random_access(tmp_path, backend):
    data = os.urandom(64 * 1024 * 3 + 777)
    path = _pack(tmp_path, {"movie.webm": data})
    r = ContainerReader(path, KEY, backend=backend)

    s = r.open_stream("movie.webm")
    try:
        assert s.seekable()
        # full read
        assert s.read() == data
        # seek to an arbitrary offset spanning a chunk boundary and read across it
        off = 64 * 1024 - 10
        s.seek(off)
        assert s.read(40) == data[off : off + 40]
        # seek from end
        s.seek(-5, os.SEEK_END)
        assert s.read() == data[-5:]
        # read in tiny pieces
        s.seek(0)
        got = b"".join(iter(lambda: s.read(7), b""))
        assert got == data
    finally:
        s.close()


def test_cross_backend_interop(tmp_path):
    """A container is portable across backends (packer uses cryptography)."""
    openssl = _openssl_backend()
    if openssl is None:
        pytest.skip("no usable OpenSSL backend on this host")

    data = os.urandom(200000)
    path = _pack(tmp_path, {"a/b.dat": data})

    assert ContainerReader(path, KEY, backend=CryptographyBackend()).read_bytes("a/b.dat") == data
    assert ContainerReader(path, KEY, backend=openssl).read_bytes("a/b.dat") == data


def test_wrong_key_fails(tmp_path):
    path = _pack(tmp_path, {"x": b"secret"})
    with pytest.raises(DecryptError):
        ContainerReader(path, b"\x01" * 32)


def test_tamper_detected(tmp_path):
    path = _pack(tmp_path, {"x": os.urandom(1000)})

    blob = bytearray(open(path, "rb").read())
    blob[80] ^= 0xFF  # flip a byte in the encrypted payload region
    open(path, "wb").write(blob)

    r = ContainerReader(path, KEY)
    with pytest.raises(DecryptError):
        r.read_bytes("x")


def test_name_normalization(tmp_path):
    path = _pack(tmp_path, {"images/bg.png": b"data"})
    r = ContainerReader(path, KEY)
    assert "images/bg.png" in r
    assert r.read_bytes("/images/bg.png") == b"data"      # leading slash
    assert r.read_bytes("images\\bg.png") == b"data"       # backslash


def test_select_backend_runs():
    assert select_backend().decrypt  # smoke: something is available
