# -*- coding: utf-8 -*-
"""Ed25519 签名（RFC 8032）纯 Python 实现。

为什么不用 cryptography / PyNaCl：
  - 只为了 32 字节验签把 5MB 的 C 扩展打进 exe 不值当，PyInstaller 还会多出
    一堆 hook 问题；
  - 验签一次几十毫秒，检查更新这种一年几十次的场景完全够用。

只暴露三个函数：
  public_key(seed32)        -> 32 字节公钥
  sign(msg, seed32)         -> 64 字节签名
  verify(sig64, msg, pk32)  -> True / False

本文件也被 CI 的 tools/sign_manifest.py 复用（私钥只在 CI 里出现）。
"""
import hashlib

__all__ = ["public_key", "sign", "verify", "SEED_LEN", "PUBLIC_KEY_LEN", "SIGNATURE_LEN"]

SEED_LEN = 32
PUBLIC_KEY_LEN = 32
SIGNATURE_LEN = 64

_Q = 2 ** 255 - 19                      # 域素数
_L = 2 ** 252 + 27742317777372353535851937790883648493   # 群的阶


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _inv(x: int) -> int:
    return pow(x, _Q - 2, _Q)


_D = (-121665 * _inv(121666)) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _x_recover(y: int) -> int:
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_BY = (4 * _inv(5)) % _Q
_BX = _x_recover(_BY)
_BASE = (_BX % _Q, _BY % _Q)


def _edwards_add(p, q):
    x1, y1 = p
    x2, y2 = q
    k = (_D * x1 * x2 * y1 * y2) % _Q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + k)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - k)
    return (x3 % _Q, y3 % _Q)


def _scalar_mult(p, e: int):
    """点倍加（递归，深度约 256 层，可接受）。"""
    if e == 0:
        return (0, 1)
    q = _scalar_mult(p, e // 2)
    q = _edwards_add(q, q)
    if e & 1:
        q = _edwards_add(q, p)
    return q


def _encode_int(y: int) -> bytes:
    return bytes((y >> (8 * i)) & 0xFF for i in range(32))


def _encode_point(p) -> bytes:
    x, y = p
    bits = list(_encode_int(y))
    bits[31] = (bits[31] & 0x7F) | ((x & 1) << 7)
    return bytes(bits)


def _decode_int(data: bytes) -> int:
    return sum(b << (8 * i) for i, b in enumerate(data))


def _decode_point(data: bytes):
    if len(data) != 32:
        return None
    y = _decode_int(data) & ((1 << 255) - 1)
    if y >= _Q:
        return None
    x = _x_recover(y)
    if (x & 1) != ((data[31] >> 7) & 1):
        x = _Q - x
    # 确认落在曲线上
    if (-x * x + y * y - 1 - _D * x * x * y * y) % _Q != 0:
        return None
    return (x, y)


def _expand(seed: bytes):
    if len(seed) != SEED_LEN:
        raise ValueError("seed 必须是 32 字节")
    h = _sha512(seed)
    a = _decode_int(h[:32])
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed: bytes) -> bytes:
    a, _ = _expand(seed)
    return _encode_point(_scalar_mult(_BASE, a))


def sign(msg: bytes, seed: bytes) -> bytes:
    a, prefix = _expand(seed)
    pk = _encode_point(_scalar_mult(_BASE, a))
    r = _decode_int(_sha512(prefix + msg)) % _L
    big_r = _encode_point(_scalar_mult(_BASE, r))
    h = _decode_int(_sha512(big_r + pk + msg)) % _L
    s = (r + h * a) % _L
    return big_r + _encode_int(s)


def verify(sig: bytes, msg: bytes, pk: bytes) -> bool:
    if len(sig) != SIGNATURE_LEN or len(pk) != PUBLIC_KEY_LEN:
        return False
    try:
        a = _decode_point(pk)
        if a is None:
            return False
        big_r = _decode_point(sig[:32])
        if big_r is None:
            return False
        s = _decode_int(sig[32:])
        if s >= _L:
            return False
        h = _decode_int(_sha512(sig[:32] + pk + msg)) % _L
        left = _scalar_mult(_BASE, s)
        right = _edwards_add(big_r, _scalar_mult(a, h))
        return left == right
    except Exception:
        return False
