import glob
import os

import pytest

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from renmori.container.format import SCRIPT_MAGIC
from renmori.script import rpyc, transform_rpyc

KEY = bytes(range(32))


def _a_real_rpyc():
    for pat in ("/Applications/renpy-*/the_question/game/*.rpyc",
                os.path.expanduser("~/Applications/renpy-*/the_question/game/*.rpyc")):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def test_transform_is_lossless_and_opaque():
    """Transform makes the script slot non-pickle, and decrypting with the
    script key restores the exact original payload (so AST is untouched)."""
    path = _a_real_rpyc()
    if not path:
        pytest.skip("no Ren'Py SDK with the_question on this host")

    raw = open(path, "rb").read()
    original = rpyc.read_slots(raw)
    assert original and 1 in original
    assert original[1][:1] == b"\x80", "expected a pickle payload in slot 1"

    transformed_raw = transform_rpyc(raw, KEY)
    transformed = rpyc.read_slots(transformed_raw)

    # Every pickle slot is now opaque (starts with our magic, not pickle PROTO).
    for sid, payload in original.items():
        if payload[:1] == b"\x80":
            assert transformed[sid][:len(SCRIPT_MAGIC)] == SCRIPT_MAGIC
            assert transformed[sid][:1] != b"\x80"

    # And it reverses exactly.
    aead = AESGCM(KEY)
    for sid, payload in transformed.items():
        if payload[:len(SCRIPT_MAGIC)] == SCRIPT_MAGIC:
            nonce = payload[len(SCRIPT_MAGIC):len(SCRIPT_MAGIC) + 12]
            ct = payload[len(SCRIPT_MAGIC) + 12:]
            assert aead.decrypt(nonce, ct, None) == original[sid]


def test_non_rpyc_passthrough():
    assert transform_rpyc(b"not an rpyc file", KEY) == b"not an rpyc file"
