"""Pure-python port of pka2xml (mircodz/pka2xml) encrypt_pka/decrypt_pka.

Pipeline (see include/pka2xml.hpp upstream):
  encrypt: zlib-compress (+4-byte BE length header) -> positional XOR ->
           Twofish-EAX seal (key {137}*16, iv {16}*16, trailing 16B tag) ->
           reversed positional XOR

The EAX variant matches Crypto++ semantics exactly (weidai11/cryptopp
eax.cpp): each component tag is a plain CMAC over a prefixed stream --
  N = CMAC(0^16 || nonce),  H = CMAC([1]_16 || header),
  C = CMAC([2]_16 || ciphertext),  tag = N xor H xor C,
and the CTR keystream is seeded with N, incremented big-endian per block.
"""

import ctypes
import struct
import zlib
from ctypes import CDLL, POINTER, Structure, c_char_p, c_int, \
    c_uint32, create_string_buffer, pointer

try:
    from twofish import Twofish
except ModuleNotFoundError:                      # pragma: no cover
    # the `twofish` wheel's wrapper imports `imp` (removed in py3.12+);
    # bind its C extension directly instead
    import importlib.util

    class _TwofishKey(Structure):
        _fields_ = [("s", (c_uint32 * 4) * 256), ("K", c_uint32 * 40)]

    _spec = importlib.util.find_spec("_twofish")
    if _spec is None:
        raise ImportError("install the `twofish` package (pip install twofish)")
    _LIB = CDLL(_spec.origin)
    _LIB.Twofish_prepare_key.argtypes = [c_char_p, c_int, POINTER(_TwofishKey)]
    _LIB.Twofish_encrypt.argtypes = [POINTER(_TwofishKey), c_char_p, c_char_p]

    class Twofish:
        def __init__(self, key):
            self._key = _TwofishKey()
            _LIB.Twofish_prepare_key(key, len(key), pointer(self._key))

        def encrypt(self, block):
            out = create_string_buffer(16)
            _LIB.Twofish_encrypt(pointer(self._key), block, out)
            return out.raw[:16]

_KEY = bytes([137]) * 16
_IV = bytes([16]) * 16


def _xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def _dbl(b):
    n = int.from_bytes(b, "big") << 1
    if b[0] & 0x80:
        n ^= 0x87
    return (n & ((1 << 128) - 1)).to_bytes(16, "big")


def _cmac(enc, m):
    L = enc(bytes(16))
    if not m or len(m) % 16:
        data = m + b"\x80" + bytes(15 - len(m) % 16)
        sub = _dbl(_dbl(L))
    else:
        data = m
        sub = _dbl(L)
    x = bytes(16)
    for i in range(0, len(data) - 16, 16):
        x = enc(_xor(x, data[i:i + 16]))
    return enc(_xor(_xor(x, data[-16:]), sub))


class _EAX:
    def __init__(self, key, iv):
        self.enc = Twofish(key).encrypt
        self._n_tag = _cmac(self.enc, bytes(16) + iv)

    def _tag(self, prefix, data):
        return _cmac(self.enc, prefix + data)

    def _keystream(self, n):
        ctr = int.from_bytes(self._n_tag, "big")
        ks = b""
        while len(ks) < n:
            ks += self.enc((ctr % (1 << 128)).to_bytes(16, "big"))
            ctr += 1
        return ks[:n]

    def seal(self, msg):
        ct = _xor(msg, self._keystream(len(msg)))
        tag = _xor(_xor(self._n_tag,
                        self._tag(bytes(15) + bytes([1]), b"")),
                   self._tag(bytes(15) + bytes([2]), ct))
        return ct + tag

    def open(self, blob):
        ct, tag = blob[:-16], blob[-16:]
        calc = _xor(_xor(self._n_tag,
                         self._tag(bytes(15) + bytes([1]), b"")),
                    self._tag(bytes(15) + bytes([2]), ct))
        if calc != tag:
            raise ValueError("EAX authentication failed")
        return _xor(ct, self._keystream(len(ct)))


def _obf_stage_outer_encrypt(data):
    n = len(data)
    out = bytearray(n)
    for i in range(n):
        out[n - 1 - i] = data[i] ^ ((n - i * n) & 0xFF)
    return bytes(out)


def _obf_stage_outer_decrypt(data):
    n = len(data)
    return bytes(data[n - 1 - i] ^ ((n - i * n) & 0xFF)
                 for i in range(n))


def _obf_stage_inner(data):
    n = len(data)
    return bytes(data[i] ^ ((n - i) & 0xFF) for i in range(n))


def compress(data):
    body = zlib.compress(data, 6)
    return struct.pack(">I", len(data)) + body


def uncompress(blob):
    size = struct.unpack(">I", blob[:4])[0]
    out = zlib.decompress(blob[4:])
    if len(out) != size:
        raise ValueError("length header mismatch")
    return out


def encrypt_pka(xml_bytes):
    packed = compress(xml_bytes)
    obf = _obf_stage_inner(packed)
    sealed = _EAX(_KEY, _IV).seal(obf)
    return _obf_stage_outer_encrypt(sealed)


def decrypt_pka(pkt_bytes):
    sealed = _obf_stage_outer_decrypt(pkt_bytes)
    obf = _EAX(_KEY, _IV).open(sealed)
    return uncompress(_obf_stage_inner(obf))
