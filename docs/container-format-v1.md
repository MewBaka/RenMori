# Container format v1 (baseline, open spec)

This is the **baseline** container format: fixed and public, at moderate
strength. Production builds run it through the closed polymorphism engine, which
randomizes the layout and key derivation per build; this spec describes the
fixed baseline that the open framework implements and tests.

All integers are little-endian. All encryption is **AES-256-GCM** (16-byte tag).

## Layout

```
+-------------------------------+  offset 0
| Header (64 bytes)             |
+-------------------------------+  offset 64
| Encrypted file payloads       |   (one region per file, in add order)
|   file A: chunk 0, chunk 1, …  |
|   file B: chunk 0, …           |
+-------------------------------+  header.index_offset
| Encrypted index (GCM)         |
+-------------------------------+  EOF
```

### Header (64 bytes)

| Off | Size | Field | Notes |
|----:|-----:|-------|-------|
| 0 | 8 | magic | `52 45 4E 4D 4F 52 49 01` (`RENMORI\x01`) |
| 8 | 2 | version | `1` |
| 10 | 2 | flags | reserved, `0` |
| 12 | 4 | chunk_size | plaintext bytes per chunk (default 65536) |
| 16 | 8 | index_offset | byte offset of the encrypted index |
| 24 | 8 | index_length | encrypted index length (plaintext + 16 tag) |
| 32 | 12 | index_nonce | GCM nonce for the index |
| 44 | 16 | container_id | random per container; salts all key derivation |
| 60 | 4 | reserved | `0` |

The first **60 bytes** of the header (everything except `reserved`) are the GCM
AAD of the index, so the header cannot be altered without breaking index
decryption.

### Index

A GCM-encrypted UTF-8 JSON object:

```json
{ "v": 1, "files": { "<name>": [data_offset, size, "<file_id hex>"], … } }
```

- `name` — Ren'Py game-relative path, forward slashes, no leading slash
  (`images/bg.png`).
- `data_offset` — absolute offset of the file's first encrypted chunk.
- `size` — plaintext size in bytes.
- `file_id` — 16 random bytes (hex), unique per file; salts the file key.

### File payload

Each file's plaintext is split into `chunk_size`-byte chunks (an empty file is
one empty chunk, so it still carries a tag). Each chunk is encrypted
independently and stored as `ciphertext || tag` (plaintext length + 16). Because
every non-final chunk is exactly `chunk_size` plaintext, chunk *i* of a file
always starts at `data_offset + i*(chunk_size + 16)` — enabling **random access
by seek** without scanning.

## Key derivation (HKDF-SHA256, RFC 5869)

```
index_key      = HKDF(ikm=master_key, salt=container_id, info="renmori/v1/index")
file_key(id)   = HKDF(ikm=master_key, salt=container_id, info="renmori/v1/file/" + id)
```

- `master_key` is 32 bytes. Where it comes from at runtime is **not** part of
  this baseline spec — the open framework takes it as input; the closed
  key-derivation logic is what hides and reconstructs it in a shipped game.
- Per-file keys mean a nonce scheme scoped to one key per file.

### Nonce (12 bytes) and AAD per chunk

```
nonce(i) = file_id[:8] || uint32_le(i)
aad(i)   = uint32_le(i) || uint8(1 if last chunk else 0)
```

The counter makes each nonce unique within a file; the unique per-file key makes
it unique across files. The AAD binds each chunk to its position and flags the
final chunk, so chunks cannot be reordered and a file cannot be silently
truncated.

## Security notes (baseline)

- Confidentiality + integrity per chunk via GCM; tamper anywhere fails decryption.
- The format is **public and fixed** — on its own it is "baseline strength". A
  universal reader is possible *if* the attacker also has the master key. The
  real barriers are (a) runtime key derivation (closed) and (b) per-build
  polymorphism (closed), neither of which is in this file.
- Not addressed here (by design): memory/screen capture. See
  [threat-model.md](threat-model.md).

## Reference implementation

- Writer: [`src/renmori/container/writer.py`](../src/renmori/container/writer.py)
- Reader + streaming: [`src/renmori/container/reader.py`](../src/renmori/container/reader.py)
- AES-GCM backends: [`src/renmori/container/crypto.py`](../src/renmori/container/crypto.py)
- Format constants / key derivation: [`src/renmori/container/format.py`](../src/renmori/container/format.py)
