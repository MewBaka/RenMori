"""
AES-256-GCM backends.

One decrypt interface, several implementations, so the same reader logic runs:

* in the build tool / tests, via the `cryptography` package;
* inside Ren'Py's bundled Python, which has no pip packages, via ctypes against
  OpenSSL (exported by librenpython on macOS/Linux) or CNG/bcrypt on Windows.

All backends implement standard AES-256-GCM, so a container packed by one is
readable by any other. `select_backend()` picks the best available.

NOTE: the ctypes backends are the *reference* runtime path for the baseline
format. The shipping closed runtime replaces them with a native, nogil
`SDL_RWops` decryptor; see docs/architecture.md.
"""

from .format import TAG_SIZE


class DecryptError(Exception):
    pass


class Backend:
    name = "base"

    def decrypt(self, key, nonce, ct_and_tag, aad):
        """Return plaintext, or raise DecryptError if the tag doesn't verify."""
        raise NotImplementedError


class CryptographyBackend(Backend):
    name = "cryptography"

    def __init__(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.exceptions import InvalidTag

        self._AESGCM = AESGCM
        self._InvalidTag = InvalidTag

    def decrypt(self, key, nonce, ct_and_tag, aad):
        try:
            return self._AESGCM(key).decrypt(nonce, ct_and_tag, aad)
        except self._InvalidTag as e:
            raise DecryptError("GCM tag mismatch") from e


class OpenSSLBackend(Backend):
    """ctypes against libcrypto. On Ren'Py mac/Linux the EVP symbols are
    exported by librenpython; elsewhere a system libcrypto is used."""

    name = "openssl"

    def __init__(self, lib=None):
        import ctypes
        import ctypes.util

        self.ctypes = ctypes

        if lib is None:
            lib = ctypes.util.find_library("crypto")
            if not lib:
                raise OSError("libcrypto not found")

        # Deliberately NOT CDLL(None): grabbing EVP symbols from the global
        # namespace can bind to a mismatched OpenSSL (e.g. the one cryptography
        # bundles) and crash the process. Inside Ren'Py we pass the explicit
        # path to librenpython, which exports its own OpenSSL.
        c = ctypes.CDLL(lib) if isinstance(lib, str) else lib

        if not hasattr(c, "EVP_aes_256_gcm"):
            raise OSError("no EVP_aes_256_gcm in %r" % lib)

        # Full prototypes are mandatory: without argtypes, ctypes marshals
        # pointers as 32-bit int and truncates them on 64-bit -> segfault.
        p = ctypes.c_void_p
        i = ctypes.c_int
        cp = ctypes.c_char_p
        ip = ctypes.POINTER(i)

        c.EVP_CIPHER_CTX_new.restype = p
        c.EVP_CIPHER_CTX_new.argtypes = []
        c.EVP_CIPHER_CTX_free.restype = None
        c.EVP_CIPHER_CTX_free.argtypes = [p]
        c.EVP_aes_256_gcm.restype = p
        c.EVP_aes_256_gcm.argtypes = []
        c.EVP_DecryptInit_ex.restype = i
        c.EVP_DecryptInit_ex.argtypes = [p, p, p, cp, cp]
        c.EVP_DecryptUpdate.restype = i
        c.EVP_DecryptUpdate.argtypes = [p, cp, ip, cp, i]
        c.EVP_DecryptFinal_ex.restype = i
        c.EVP_DecryptFinal_ex.argtypes = [p, cp, ip]
        c.EVP_CIPHER_CTX_ctrl.restype = i
        c.EVP_CIPHER_CTX_ctrl.argtypes = [p, i, i, cp]

        self.c = c
        self.EVP_CTRL_GCM_SET_IVLEN = 0x9
        self.EVP_CTRL_GCM_SET_TAG = 0x11

    def decrypt(self, key, nonce, ct_and_tag, aad):
        ctypes = self.ctypes
        c = self.c

        if len(ct_and_tag) < TAG_SIZE:
            raise DecryptError("chunk shorter than tag")

        ct = ct_and_tag[:-TAG_SIZE]
        tag = ct_and_tag[-TAG_SIZE:]

        ctx = c.EVP_CIPHER_CTX_new()
        if not ctx:
            raise DecryptError("EVP_CIPHER_CTX_new failed")

        try:
            null = ctypes.c_void_p(0)
            if c.EVP_DecryptInit_ex(ctx, c.EVP_aes_256_gcm(), null, None, None) != 1:
                raise DecryptError("DecryptInit(cipher) failed")
            if c.EVP_CIPHER_CTX_ctrl(ctx, self.EVP_CTRL_GCM_SET_IVLEN, len(nonce), None) != 1:
                raise DecryptError("set ivlen failed")
            if c.EVP_DecryptInit_ex(ctx, None, null, key, nonce) != 1:
                raise DecryptError("DecryptInit(key) failed")

            outlen = ctypes.c_int(0)

            if aad:
                if c.EVP_DecryptUpdate(ctx, None, ctypes.byref(outlen), aad, len(aad)) != 1:
                    raise DecryptError("aad update failed")

            # Note: the AAD update above leaves outlen set to the AAD length, so
            # take the plaintext length only from the ciphertext update.
            produced = 0
            out = ctypes.create_string_buffer(len(ct) if ct else 1)
            if ct:
                if c.EVP_DecryptUpdate(ctx, out, ctypes.byref(outlen), ct, len(ct)) != 1:
                    raise DecryptError("decrypt update failed")
                produced = outlen.value

            if c.EVP_CIPHER_CTX_ctrl(ctx, self.EVP_CTRL_GCM_SET_TAG, TAG_SIZE, tag) != 1:
                raise DecryptError("set tag failed")

            final = ctypes.create_string_buffer(16)
            finlen = ctypes.c_int(0)
            if c.EVP_DecryptFinal_ex(ctx, final, ctypes.byref(finlen)) != 1:
                raise DecryptError("GCM tag mismatch")

            return out.raw[:produced] + final.raw[: finlen.value]
        finally:
            c.EVP_CIPHER_CTX_free(ctx)


class CNGBackend(Backend):
    """ctypes against Windows CNG (bcrypt.dll). AES-GCM is hardware-accelerated
    on every Windows since Vista. Verified on Windows (see M4)."""

    name = "cng"

    def __init__(self):
        import ctypes
        from ctypes import wintypes  # noqa: F401  (import guards non-Windows)

        self.ctypes = ctypes
        self.bcrypt = ctypes.WinDLL("bcrypt.dll")

    def decrypt(self, key, nonce, ct_and_tag, aad):  # pragma: no cover - Windows only
        ctypes = self.ctypes
        bcrypt = self.bcrypt

        if len(ct_and_tag) < TAG_SIZE:
            raise DecryptError("chunk shorter than tag")

        ct = ct_and_tag[:-TAG_SIZE]
        tag = ct_and_tag[-TAG_SIZE:]

        BCRYPT_AES_ALGORITHM = "AES"
        BCRYPT_CHAIN_MODE_GCM = "ChainingModeGCM"

        halg = ctypes.c_void_p()
        status = bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(halg), BCRYPT_AES_ALGORITHM, None, 0)
        if status != 0:
            raise DecryptError("BCryptOpenAlgorithmProvider 0x%x" % (status & 0xFFFFFFFF))

        try:
            mode = BCRYPT_CHAIN_MODE_GCM.encode("utf-16-le") + b"\x00\x00"
            status = bcrypt.BCryptSetProperty(halg, "ChainingMode", mode, len(mode), 0)
            if status != 0:
                raise DecryptError("BCryptSetProperty 0x%x" % (status & 0xFFFFFFFF))

            hkey = ctypes.c_void_p()
            kbuf = ctypes.create_string_buffer(key, len(key))
            status = bcrypt.BCryptGenerateSymmetricKey(halg, ctypes.byref(hkey), None, 0, kbuf, len(key), 0)
            if status != 0:
                raise DecryptError("BCryptGenerateSymmetricKey 0x%x" % (status & 0xFFFFFFFF))

            try:
                info = _BCRYPT_AUTH_INFO(ctypes, nonce, aad, tag)
                out = ctypes.create_string_buffer(len(ct) if ct else 1)
                done = ctypes.c_ulong(0)

                status = bcrypt.BCryptDecrypt(
                    hkey,
                    ctypes.create_string_buffer(ct, len(ct)) if ct else None,
                    len(ct),
                    ctypes.byref(info.struct),
                    None,
                    0,
                    out,
                    len(ct),
                    ctypes.byref(done),
                    0,
                )
                if status != 0:
                    raise DecryptError("GCM tag mismatch (0x%x)" % (status & 0xFFFFFFFF))

                return out.raw[: done.value]
            finally:
                bcrypt.BCryptDestroyKey(hkey)
        finally:
            bcrypt.BCryptCloseAlgorithmProvider(halg, 0)


class _BCRYPT_AUTH_INFO:  # pragma: no cover - Windows only
    """BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO, kept alive with its buffers."""

    def __init__(self, ctypes, nonce, aad, tag):
        self._nonce = ctypes.create_string_buffer(nonce, len(nonce))
        self._aad = ctypes.create_string_buffer(aad, len(aad)) if aad else None
        self._tag = ctypes.create_string_buffer(tag, len(tag))

        class INFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("dwInfoVersion", ctypes.c_ulong),
                ("pbNonce", ctypes.c_void_p),
                ("cbNonce", ctypes.c_ulong),
                ("pbAuthData", ctypes.c_void_p),
                ("cbAuthData", ctypes.c_ulong),
                ("pbTag", ctypes.c_void_p),
                ("cbTag", ctypes.c_ulong),
                ("pbMacContext", ctypes.c_void_p),
                ("cbMacContext", ctypes.c_ulong),
                ("cbAAD", ctypes.c_ulong),
                ("cbData", ctypes.c_ulonglong),
                ("dwFlags", ctypes.c_ulong),
            ]

        s = INFO()
        ctypes.memset(ctypes.byref(s), 0, ctypes.sizeof(s))
        s.cbSize = ctypes.sizeof(s)
        s.dwInfoVersion = 1
        s.pbNonce = ctypes.cast(self._nonce, ctypes.c_void_p)
        s.cbNonce = len(nonce)
        if aad:
            s.pbAuthData = ctypes.cast(self._aad, ctypes.c_void_p)
            s.cbAuthData = len(aad)
        s.pbTag = ctypes.cast(self._tag, ctypes.c_void_p)
        s.cbTag = len(tag)
        self.struct = s


def select_backend():
    """Pick the best available backend, most-preferred first."""

    errors = []
    for factory in (CryptographyBackend, OpenSSLBackend, _cng_if_windows):
        if factory is None:
            continue
        try:
            return factory()
        except Exception as e:  # noqa: BLE001 - we want to try the next one
            errors.append("%s: %s" % (getattr(factory, "__name__", factory), e))

    raise DecryptError("no AES-GCM backend available: " + "; ".join(errors))


def _cng_if_windows():
    import sys

    if sys.platform != "win32":
        raise OSError("not Windows")
    return CNGBackend()


def runtime_lib_candidates(exe_dir):
    """
    Candidate librenpython libraries beside the Python executable. Inside Ren'Py,
    this is the correctly-built OpenSSL (macOS/Linux) the runtime loads by
    explicit path (never CDLL(None)).
    """
    import glob
    import os

    return sorted(glob.glob(os.path.join(exe_dir, "librenpython.*")))
