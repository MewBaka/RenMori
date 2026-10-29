"""
Build-side writer for container format v1.

Runs in the developer / CI environment, so it may use the `cryptography`
package. Nothing in here ships inside the game.
"""

import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import format as fmt


class ContainerWriter:
    """
    Packs files into a single encrypted container.

        with ContainerWriter(path, master_key) as w:
            w.add_file("images/bg.png", "/abs/path/bg.png")
    """

    def __init__(self, path, master_key, chunk_size=fmt.DEFAULT_CHUNK_SIZE):
        if len(master_key) != fmt.KEY_SIZE:
            raise ValueError("master key must be %d bytes" % fmt.KEY_SIZE)

        self.path = path
        self.master_key = master_key
        self.chunk_size = chunk_size
        self.container_id = os.urandom(fmt.CONTAINER_ID_SIZE)

        self.files = {}
        self.f = open(path, "wb")
        self.f.write(b"\0" * fmt.HEADER_SIZE)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.close()
        else:
            self.f.close()

    def add_file(self, name, source_path):
        with open(source_path, "rb") as src:
            self._add_stream(name, src, os.path.getsize(source_path))

    def add_bytes(self, name, data):
        import io

        self._add_stream(name, io.BytesIO(data), len(data))

    def _add_stream(self, name, src, size):
        name = fmt.normalize_name(name)

        if name in self.files:
            raise ValueError("duplicate entry %r" % name)

        file_id = os.urandom(fmt.FILE_ID_SIZE)
        aead = AESGCM(fmt.file_key(self.master_key, self.container_id, file_id))

        offset = self.f.tell()
        count = fmt.chunk_count(size, self.chunk_size)

        for i in range(count):
            chunk = src.read(self.chunk_size)
            is_last = i == count - 1

            if not is_last and len(chunk) != self.chunk_size:
                raise IOError("%s changed size while packing" % name)

            self.f.write(aead.encrypt(fmt.chunk_nonce(file_id, i), chunk, fmt.chunk_aad(i, is_last)))

        if src.read(1):
            raise IOError("%s changed size while packing" % name)

        self.files[name] = [offset, size, file_id.hex()]

    def close(self):
        index = json.dumps({"v": fmt.VERSION, "files": self.files}, separators=(",", ":")).encode("utf-8")

        index_offset = self.f.tell()
        index_nonce = os.urandom(12)

        header = fmt.Header(
            chunk_size=self.chunk_size,
            index_offset=index_offset,
            index_length=len(index) + fmt.TAG_SIZE,
            index_nonce=index_nonce,
            container_id=self.container_id,
        )

        packed = header.pack()
        aead = AESGCM(fmt.index_key(self.master_key, self.container_id))
        self.f.write(aead.encrypt(index_nonce, index, packed[: fmt.HEADER_AAD_SIZE]))

        self.f.seek(0)
        self.f.write(packed)
        self.f.close()
