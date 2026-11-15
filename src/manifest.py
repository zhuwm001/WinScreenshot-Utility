# -*- coding: utf-8 -*-
"""更新清单 latest.json 的生成与验签。

为什么要有清单：
    光靠 GitHub Release 不够。下载地址和 sha256 都来自 GitHub，一旦账号被盗、
    Release 被换成别人的包，客户端没有任何办法分辨。所以让 CI 用**只有作者手里
    有的私钥**对「版本 + 文件名 + 大小 + sha256 + 下载地址」签一次名，客户端
    内置公钥验签：签名过不了就一个字都不下。

清单长这样（latest.json，作为 Release 附件发布）：
    {
      "payload":   { "schema": 1, "repo": "...", "version": "1.1.1", ... },
      "signature": "<base64 的 64 字节 Ed25519 签名>"
    }

签名覆盖的是 payload 的**规范序列化**（键排序、无空格、UTF-8），
两端必须用同一个 canonical() 函数，否则验签必然失败。
"""
import base64
import json

import ed25519

# 对应私钥存在 GitHub 仓库 Secret「UPDATE_SIGNING_KEY」，只用于 CI 签名。
# 换密钥要同时改这里 + 仓库 Secret，并重发一版。
PUBKEY_HEX = "e426b85b588df609626d88614b82f489ed0594cec13cfa9167454a3670a2fa30"

SCHEMA = 1
SIGNATURE_LEN = 64


def canonical(payload) -> bytes:
    """payload -> 规范化字节串（键排序、紧凑分隔符、保留中文）。"""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def build(payload: dict, seed: bytes) -> dict:
    """签名，返回可直接写盘的 dict。"""
    sig = ed25519.sign(canonical(payload), seed)
    return {"payload": payload, "signature": base64.b64encode(sig).decode("ascii")}


def _fail(reason):
    return None, reason


def verify_document(doc, pubkey_hex: str = PUBKEY_HEX):
    """校验整份清单。返回 (payload, "") 或 (None, 失败原因)。"""
    if not isinstance(doc, dict):
        return _fail("清单格式不对")
    payload = doc.get("payload")
    signature = doc.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        return _fail("清单缺少 payload 或 signature")
    try:
        sig = base64.b64decode(signature.strip(), validate=True)
    except Exception:
        return _fail("签名不是合法的 base64")
    if len(sig) != SIGNATURE_LEN:
        return _fail("签名长度不对")
    try:
        pk = bytes.fromhex(pubkey_hex)
    except ValueError:
        return _fail("内置公钥格式错误")

    if not ed25519.verify(sig, canonical(payload), pk):
        return _fail("签名校验失败：这份清单不是作者发布的，已拒绝")
    return verify_payload(payload)


def verify_payload(payload: dict):
    """签名没问题后再看内容合不合理，挡住残缺 / 越权的东西。"""
    if payload.get("schema") != SCHEMA:
        return _fail("清单版本不认识（schema=%r）" % (payload.get("schema"),))
    version = str(payload.get("version") or "").strip()
    if not version:
        return _fail("清单没有版本号")

    asset = payload.get("asset") or {}
    if not isinstance(asset, dict):
        return _fail("清单里的 asset 字段不对")
    name = str(asset.get("name") or "")
    url = str(asset.get("url") or "")
    digest = str(asset.get("sha256") or "").lower()
    size = asset.get("size") or 0
    if not name.lower().endswith(".exe"):
        return _fail("清单里的安装包不是 exe")
    if not url.startswith("https://"):
        return _fail("安装包地址必须走 https")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return _fail("清单里的 sha256 不合法")
    try:
        size = int(size)
    except (TypeError, ValueError):
        return _fail("清单里的文件大小不合法")
    if size <= 0:
        return _fail("清单里的文件大小不合法")
    return payload, ""
