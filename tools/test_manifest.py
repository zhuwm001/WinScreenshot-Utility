# -*- coding: utf-8 -*-
"""签名清单自检：算法对不对、篡改能不能挡住、内容规则有没有生效。"""
import base64
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import ed25519
import manifest
import update

PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  [ok]   %s%s" % (name, ("  " + detail) if detail else ""))
    else:
        FAIL += 1
        print("  [FAIL] %s%s" % (name, ("  " + detail) if detail else ""))


def make_payload(version="9.9.9", **over):
    p = {
        "schema": 1,
        "repo": "tiamma46/WinScreenshot-Utility",
        "version": version,
        "tag": "v" + version,
        "published_at": "2026-11-16T00:00:00Z",
        "notes": "### 更新内容\n\n- 修了点东西",
        "asset": {
            "name": "WoAiJieTu-Setup-v%s.exe" % version,
            "size": 27812824,
            "sha256": "a" * 64,
            "url": ("https://github.com/tiamma46/WinScreenshot-Utility/releases/"
                    "download/v%s/WoAiJieTu-Setup-v%s.exe" % (version, version)),
        },
    }
    p.update(over)
    return p


print("== RFC 8032 测试向量 ==")
seed1 = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
check("公钥算法", ed25519.public_key(seed1).hex() ==
      "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
check("签名算法", ed25519.sign(b"", seed1).hex() ==
      "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
      "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")

print("\n== 规范化序列化 ==")
a = manifest.canonical({"b": 1, "a": "中文", "c": [1, 2]})
b = manifest.canonical({"c": [1, 2], "a": "中文", "b": 1})
check("键顺序无关", a == b, a.decode("utf-8"))
check("中文不转义", "中文" in a.decode("utf-8"))
check("无多余空格", b" " not in a)

print("\n== 签名 / 验签 ==")
seed = os.urandom(32)
pk = ed25519.public_key(seed).hex()
payload = make_payload()
doc = manifest.build(payload, seed)
ok, reason = manifest.verify_document(doc, pk)
check("签名清单可通过", ok is not None, reason or "版本 %s" % (ok or {}).get("version"))

print("\n== 篡改必须被拦住 ==")
bad = copy.deepcopy(doc)
bad["payload"]["version"] = "0.0.1"
ok, reason = manifest.verify_document(bad, pk)
check("改版本号", ok is None, reason)

bad = copy.deepcopy(doc)
bad["payload"]["asset"]["sha256"] = "b" * 64
ok, reason = manifest.verify_document(bad, pk)
check("改 sha256", ok is None, reason)

bad = copy.deepcopy(doc)
bad["payload"]["asset"]["url"] = "https://evil.example.com/x.exe"
ok, reason = manifest.verify_document(bad, pk)
check("改下载地址", ok is None, reason)

bad = copy.deepcopy(doc)
raw = bytearray(base64.b64decode(bad["signature"]))
raw[0] ^= 1
bad["signature"] = base64.b64encode(bytes(raw)).decode()
ok, reason = manifest.verify_document(bad, pk)
check("翻转签名一个 bit", ok is None, reason)

bad = copy.deepcopy(doc)
bad["signature"] = "not-base64!!"
ok, reason = manifest.verify_document(bad, pk)
check("签名不是 base64", ok is None, reason)

bad = copy.deepcopy(doc)
bad["signature"] = base64.b64encode(b"x" * 32).decode()
ok, reason = manifest.verify_document(bad, pk)
check("签名长度不对", ok is None, reason)

print("\n== 换一把钥匙签（模拟别人伪造）==")
other = manifest.build(payload, os.urandom(32))
ok, reason = manifest.verify_document(other, pk)
check("别人的私钥签的清单", ok is None, reason)

print("\n== 内容规则 ==")
cases = [
    ("schema 不对", {"schema": 2}),
    ("没有版本号", {"version": ""}),
    ("附件不是 exe", {"asset": dict(make_payload()["asset"], name="x.zip")}),
    ("走 http", {"asset": dict(make_payload()["asset"], url="http://a.com/x.exe")}),
    ("sha256 长度不对", {"asset": dict(make_payload()["asset"], sha256="abc")}),
    ("大小为 0", {"asset": dict(make_payload()["asset"], size=0)}),
]
for label, over in cases:
    d = manifest.build(make_payload(**over), seed)
    ok, reason = manifest.verify_document(d, pk)
    check(label, ok is None, reason)

print("\n== 下载地址白名单 ==")
good = "https://github.com/o/r/releases/download/v1/a.exe"
check("github.com 通过", update.url_allowed(good))
check("objects.githubusercontent.com 通过",
      update.url_allowed("https://objects.githubusercontent.com/xx/a.exe?sig=1"))
check("别的域名拒绝", not update.url_allowed("https://evil.com/a.exe"))
check("伪装子域拒绝", not update.url_allowed("https://github.com.evil.com/a.exe"))
check("http 拒绝", not update.url_allowed("http://github.com/o/r/a.exe"))
check("空地址拒绝", not update.url_allowed(""))

print("\n== 版本比较 ==")
p = make_payload("1.1.1")
check("1.1.0 -> 1.1.1 有新版", update.parse_manifest(p, "1.1.0") is not None)
check("1.1.1 -> 1.1.1 无新版", update.parse_manifest(p, "1.1.1") is None)
check("1.1.2 -> 1.1.1 无新版", update.parse_manifest(p, "1.1.2") is None)
info = update.parse_manifest(p, "1.0.9")
check("sha256 带到 ReleaseInfo", info and info.digest.startswith("sha256:"))
check("标记为已签名", info and info.signed)
check("更新说明去了井号", info and "###" not in info.notes_text,
      (info.notes_text if info else "")[:40].replace("\n", " / "))

print("\n== 现有安装包能通过模拟签名 ==")
exe = os.path.join(ROOT, "dist", "我爱截图", "我爱截图.exe")
if os.path.exists(exe):
    sys.path.insert(0, HERE)
    import sign_manifest
    real = sign_manifest.build_payload(exe, "1.1.1", update.REPO, "v1.1.1",
                                       "- 测试用更新说明\n- 第二行")
    doc = manifest.build(real, seed)
    ok, reason = manifest.verify_document(doc, pk)
    check("真实 exe 的清单可验签", ok is not None, reason)
    check("sha256 与独立计算一致",
          ok and ok["asset"]["sha256"] == update.sha256_file(exe))
    check("大小与文件一致", ok and ok["asset"]["size"] == os.path.getsize(exe))
    check("下载地址拼得对",
          ok and ok["asset"]["url"].endswith("/v1.1.1/" + os.path.basename(exe)),
          ok and ok["asset"]["url"][-60:])
else:
    print("  （跳过：%s 不存在）" % exe)

print("\n通过 %d / 失败 %d" % (PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
