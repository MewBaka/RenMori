"""
Minimal reader/writer for the RPYC2 slot container (stdlib only).

An `.rpyc` file is `RENPY RPC2` + three 12-byte slot entries (slot_id, start,
length), then zlib-compressed payloads, optionally an md5 trailer. Ren'Py keeps
the real `(data, stmts)` pickle in slot 1 and static-transform data in slot 2.

We only touch the slot payloads; the engine's own ``read_rpyc_data`` reads the
result unchanged.
"""

import struct
import zlib

RPYC2_HEADER = b"RENPY RPC2"
_MAX_SLOTS = 3


def read_slots(raw):
    """Return {slot_id: decompressed_payload} or None if not an RPYC2 file."""
    if raw[: len(RPYC2_HEADER)] != RPYC2_HEADER:
        return None

    slots = {}
    pos = len(RPYC2_HEADER)
    while True:
        slot_id, start, length = struct.unpack("III", raw[pos : pos + 12])
        if slot_id == 0:
            break
        slots[slot_id] = zlib.decompress(raw[start : start + length])
        pos += 12

    return slots


def build(slots):
    """Rebuild an RPYC2 file from {slot_id: payload}. Drops the md5 trailer,
    which only matters when a matching .rpy is present (never in a release)."""
    if len(slots) > _MAX_SLOTS:
        raise ValueError("too many slots: %d" % len(slots))

    header_len = len(RPYC2_HEADER) + 12 * _MAX_SLOTS
    out = bytearray(RPYC2_HEADER)
    out += b"\x00" * (12 * _MAX_SLOTS)

    payloads = bytearray()
    for i, slot_id in enumerate(sorted(slots)):
        comp = zlib.compress(slots[slot_id], 3)
        start = header_len + len(payloads)
        struct.pack_into("III", out, len(RPYC2_HEADER) + 12 * i, slot_id, start, len(comp))
        payloads += comp

    out += payloads
    return bytes(out)
