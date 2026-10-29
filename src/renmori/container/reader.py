"""
Runtime reader for container format v1.

Stdlib-only apart from the crypto backend (chosen at runtime). Each open stream
owns its own file handle so concurrent loads from Ren'Py's worker threads are
safe.
"""

import io
import json

from . import format as fmt
from .crypto import DecryptError, select_backend


class ContainerReader:
    def __init__(self, path, master_key, backend=None):
        self.path = path
        self.master_key = master_key
        self.backend = backend or select_backend()

        with open(path, "rb") as f:
            header_bytes = f.read(fmt.HEADER_SIZE)
            self.header = fmt.Header.unpack(header_bytes)
            f.seek(self.header.index_offset)
            enc_index = f.read(self.header.index_length)

        key = fmt.index_key(master_key, self.header.container_id)
        raw = self.backend.decrypt(key, self.header.index_nonce, enc_index, header_bytes[: fmt.HEADER_AAD_SIZE])
        index = json.loads(raw.decode("utf-8"))

        if index.get("v") != fmt.VERSION:
            raise fmt.FormatError("index version mismatch")

        # name -> (data_offset, size, file_id bytes)
        self._files = {}
        for name, (offset, size, file_id_hex) in index["files"].items():
            self._files[name] = (offset, size, bytes.fromhex(file_id_hex))

    def __contains__(self, name):
        return fmt.normalize_name(name) in self._files

    def names(self):
        return list(self._files)

    def size(self, name):
        return self._files[fmt.normalize_name(name)][1]

    def _entry(self, name):
        name = fmt.normalize_name(name)
        try:
            return name, self._files[name]
        except KeyError:
            raise KeyError(name)

    def read_bytes(self, name):
        name, (offset, size, file_id) = self._entry(name)
        key = fmt.file_key(self.master_key, self.header.container_id, file_id)
        chunk_size = self.header.chunk_size
        count = fmt.chunk_count(size, chunk_size)

        out = bytearray()
        with open(self.path, "rb") as f:
            f.seek(offset)
            for i in range(count):
                plain_len = _plain_len(i, count, size, chunk_size)
                enc = f.read(plain_len + fmt.TAG_SIZE)
                out += self.backend.decrypt(key, fmt.chunk_nonce(file_id, i), enc, fmt.chunk_aad(i, i == count - 1))

        if len(out) != size:
            raise DecryptError("decrypted size mismatch for %r" % name)

        return bytes(out)

    def open_stream(self, name):
        name, (offset, size, file_id) = self._entry(name)
        key = fmt.file_key(self.master_key, self.header.container_id, file_id)
        return ChunkDecryptingStream(self.path, self.backend, key, file_id, offset, size, self.header.chunk_size)


def _plain_len(i, count, size, chunk_size):
    if i < count - 1:
        return chunk_size
    return size - (count - 1) * chunk_size


class ChunkDecryptingStream(io.RawIOBase):
    """
    Seekable read-only stream that decrypts one chunk at a time, caching the
    most recently used chunk. Deliberately exposes no ``.name`` or ``.raw``
    attribute, so Ren'Py's ``to_rwops`` cannot try to reopen it from disk (see
    docs/loader-hook.md).
    """

    def __init__(self, path, backend, key, file_id, base_offset, size, chunk_size):
        self._backend = backend
        self._key = key
        self._file_id = file_id
        self._base = base_offset
        self._size = size
        self._chunk_size = chunk_size
        self._count = fmt.chunk_count(size, chunk_size)
        self._pos = 0

        self._cached_index = -1
        self._cached_plain = b""

        self._f = open(path, "rb")

    # --- io.RawIOBase contract ---

    def readable(self):
        return True

    def seekable(self):
        return True

    def writable(self):
        return False

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            pos = offset
        elif whence == io.SEEK_CUR:
            pos = self._pos + offset
        elif whence == io.SEEK_END:
            pos = self._size + offset
        else:
            raise ValueError("bad whence %r" % whence)

        self._pos = max(0, pos)
        return self._pos

    def tell(self):
        return self._pos

    def readinto(self, b):
        if self._pos >= self._size:
            return 0

        want = min(len(b), self._size - self._pos)
        written = 0

        while written < want:
            index = (self._pos) // self._chunk_size
            plain = self._chunk(index)
            start = self._pos - index * self._chunk_size
            take = min(len(plain) - start, want - written)
            b[written : written + take] = plain[start : start + take]
            written += take
            self._pos += take

        return written

    def _chunk(self, index):
        if index == self._cached_index:
            return self._cached_plain

        enc_offset = self._base + index * (self._chunk_size + fmt.TAG_SIZE)
        plain_len = _plain_len(index, self._count, self._size, self._chunk_size)

        self._f.seek(enc_offset)
        enc = self._f.read(plain_len + fmt.TAG_SIZE)

        plain = self._backend.decrypt(
            self._key,
            fmt.chunk_nonce(self._file_id, index),
            enc,
            fmt.chunk_aad(index, index == self._count - 1),
        )

        self._cached_index = index
        self._cached_plain = plain
        return plain

    def close(self):
        try:
            if not self.closed:
                self._f.close()
        finally:
            super().close()
