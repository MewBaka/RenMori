"""
Baseline container format v1 (open spec). See docs/container-format-v1.md.

This module is stdlib-only on purpose: it is imported both by the build tool
and by the runtime inside Ren'Py's bundled Python, which has no pip packages.
"""

import hashlib
import hmac
import struct

MAGIC = b"RENMORI\x01"
VERSION = 1

# Marks a script slot payload that renmori re-encrypted under the independent
# script key (see docs/script-layer.md). A normal pickle payload starts with
# 0x80 (PROTO), so this never collides.
SCRIPT_MAGIC = b"RMSC\x01"
HEADER_SIZE = 64
TAG_SIZE = 16
DEFAULT_CHUNK_SIZE = 64 * 1024
KEY_SIZE = 32
FILE_ID_SIZE = 16
CONTAINER_ID_SIZE = 16

# magic, version, flags, chunk_size, index_offset, index_length,
# index_nonce, container_id, reserved
_HEADER = struct.Struct("<8sHHIQQ12s16s4s")
assert _HEADER.size == HEADER_SIZE

# The part of the header that is bound to the index as AAD
# (everything except the trailing reserved bytes).
HEADER_AAD_SIZE = HEADER_SIZE - 4


class FormatError(Exception):
    pass


class Header:
    __slots__ = ("chunk_size", "index_offset", "index_length", "index_nonce", "container_id", "flags")

    def __init__(self, chunk_size, index_offset, index_length, index_nonce, container_id, flags=0):
        self.chunk_size = chunk_size
        self.index_offset = index_offset
        self.index_length = index_length
        self.index_nonce = index_nonce
        self.container_id = container_id
        self.flags = flags

    def pack(self):
        return _HEADER.pack(
            MAGIC,
            VERSION,
            self.flags,
            self.chunk_size,
            self.index_offset,
            self.index_length,
            self.index_nonce,
            self.container_id,
            b"\0\0\0\0",
        )

    @classmethod
    def unpack(cls, data):
        if len(data) < HEADER_SIZE:
            raise FormatError("truncated header")

        magic, version, flags, chunk_size, index_offset, index_length, index_nonce, container_id, _ = _HEADER.unpack_from(data)

        if magic != MAGIC:
            raise FormatError("not a renmori container")
        if version != VERSION:
            raise FormatError("unsupported container version %d" % version)
        if chunk_size <= 0:
            raise FormatError("bad chunk size")

        return cls(chunk_size, index_offset, index_length, index_nonce, container_id, flags)


def hkdf_sha256(ikm, salt, info, length=KEY_SIZE):
    """RFC 5869 HKDF with SHA-256."""

    prk = hmac.new(salt, ikm, hashlib.sha256).digest()

    out = b""
    block = b""
    counter = 1

    while len(out) < length:
        block = hmac.new(prk, block + info + bytes((counter,)), hashlib.sha256).digest()
        out += block
        counter += 1

    return out[:length]


def index_key(master_key, container_id):
    return hkdf_sha256(master_key, container_id, b"renmori/v1/index")


def file_key(master_key, container_id, file_id):
    return hkdf_sha256(master_key, container_id, b"renmori/v1/file/" + file_id)


def chunk_count(size, chunk_size):
    """An empty file still has one (empty) chunk, so it carries a tag."""

    if size == 0:
        return 1

    return (size + chunk_size - 1) // chunk_size


def chunk_nonce(file_id, index):
    return file_id[:8] + struct.pack("<I", index)


def chunk_aad(index, is_last):
    # Binds each chunk to its position and marks the last one, so chunks can't be
    # reordered and a file can't be silently truncated.
    return struct.pack("<IB", index, 1 if is_last else 0)


def encrypted_size(size, chunk_size):
    return size + chunk_count(size, chunk_size) * TAG_SIZE


def normalize_name(name):
    """Container entry names use Ren'Py's game-relative form: forward slashes, no leading slash."""

    return name.replace("\\", "/").lstrip("/")
