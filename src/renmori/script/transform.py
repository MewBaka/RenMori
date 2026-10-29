"""
Build-side script transform: re-encrypt each compiled-script slot payload under
the independent script key, so that exposing the container's *contents* (e.g. a
leak of the container master key) still does not yield a standard, decompilable
``.rpyc``. The runtime reverses it just before Ren'Py unpickles.

The payload is a standard pickle (starts with 0x80); we replace it with
``SCRIPT_MAGIC || nonce || AES-256-GCM(script_key, payload)``. Reversible and
lossless, so AST semantics are untouched.

Stronger per-build AST class-name randomization is the closed polymorphism
engine's job; see docs/script-layer.md for its specified mechanism.
"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..container.format import SCRIPT_MAGIC
from . import rpyc

SCRIPT_EXTENSIONS = (".rpyc", ".rpymc")


def transform_rpyc(raw, script_key):
    """Return transformed `.rpyc` bytes, or the input unchanged if it isn't an
    RPYC2 file we recognize."""
    slots = rpyc.read_slots(raw)
    if slots is None:
        return raw

    aead = AESGCM(script_key)
    new_slots = {}

    for slot_id, payload in slots.items():
        if payload[:1] == b"\x80":  # a pickle PROTO opcode: this is AST data
            nonce = os.urandom(12)
            ct = aead.encrypt(nonce, payload, None)
            new_slots[slot_id] = SCRIPT_MAGIC + nonce + ct
        else:
            new_slots[slot_id] = payload

    return rpyc.build(new_slots)
