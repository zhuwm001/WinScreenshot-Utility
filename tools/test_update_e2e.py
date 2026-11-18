# -*- coding: utf-8 -*-
"""更新检查链路自检（不联网）：签名清单 -> 验签 -> 比版本 -> 发信号。

为什么不联网也要跑这一套：
    「重新打开软件却没查到新版本」这类问题，一半出在时机（查没查），
    另一半出在链路（查到了但认不出）。这里把链路钉死：给一段**真的签过名**
    的清单，UpdateChecker 必须走到 found / latest，而且 ReleaseInfo 里的
    版本、安装包、sha256 都得对。

用法：
    python tools/test_update_e2e.py
"""
import base64
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import qt_env  # noqa: E402  Qt 平台插件路径统一处理，避免弹 no Qt platform plugin
qt_env.setup()

from PyQt5.QtWidgets import QApplication        # noqa: E402

import ed25519                                  # noqa: E402
import manifest                                 # noqa: E402
import update as up                             # noqa: E402

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


# 测试用的密钥对（一次性），只在这个自检里用
SEED = bytes(range(32))
PUB = ed25519.public_key(SEED).hex()


def signed_doc(version="9.9.9", **kw):
    payload = {
        "schema": 1,
        "repo": "zhuwm001/WinScreenshot-Utility",
        "version": version,
        "tag": "v" + version,
        "published_at": "2026-11-17T03:00:00Z",
        "notes": "### 更新内容\n\n- 修好了更新检查\n",
        "asset": {
            "name": "WoAiJieTu-Setup-v%s.exe" % version,
            "size": 28948431,
            "sha256": "a" * 64,
            "url": ("https://github.com/zhuwm001/WinScreenshot-Utility/releases/"
                    "download/v%s/WoAiJieTu-Setup-v%s.exe" % (version, version)),
        },
    }
    payload.update(kw)
    return manifest.build(payload, SEED)


def run(doc, current):
    """把清单喂给真的 UpdateChecker，收集它发出的信号。"""
    app = QApplication.instance()
    old_verify = up.manifest.verify_document
    # verify_document 的公钥是默认参数，改常量没用：包一层把测试公钥传进去
    up.manifest.verify_document = lambda d: old_verify(d, PUB)
    out = {}
    try:
        checker = up.UpdateChecker()
        checker.found.connect(lambda info: out.update(kind="found", info=info))
        checker.latest.connect(lambda v: out.update(kind="latest", ver=v))
        checker.failed.connect(lambda m: out.update(kind="failed", msg=m))
        data = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        checker._handle_bytes(data)
        for _ in range(20):
            app.processEvents()
            time.sleep(0.01)
    finally:
        up.manifest.verify_document = old_verify
    return out


def main():
    app = QApplication(sys.argv)        # 全程只建一个，别让它被回收
    print("更新检查链路自检（不联网）")

    print("\n== 清楚的清单：有新版本 ==")
    out = run(signed_doc("9.9.9"), "1.2.0")
    check("判定为发现新版本", out.get("kind") == "found", str(out.get("kind")))
    info = out.get("info")
    if info is not None:
        check("版本号对", info.version == "9.9.9", info.version)
        check("安装包名对", info.asset_name.endswith("v9.9.9.exe"), str(info.asset_name))
        check("带 sha256", info.sha256 == "a" * 64)
        check("标记为已签名", bool(info.signed))
        check("更新说明已排版", "更新内容" in info.notes_text and "#" not in info.notes_text)

    print("\n== 同版本 / 更旧的清单：已是最新 ==")
    out = run(signed_doc("1.2.0"), "1.2.0")
    check("同版本判定为最新", out.get("kind") == "latest", str(out.get("kind")))
    out = run(signed_doc("1.1.6"), "1.2.0")
    check("更旧的版本不提示更新", out.get("kind") == "latest", str(out.get("kind")))

    print("\n== 签名不对：绝不认（这是防掉包的最后一道） ==")
    doc = signed_doc("9.9.9")
    doc["payload"]["asset"]["url"] = "https://evil.example.com/x.exe"   # 改了内容
    out = run(doc, "1.2.0")
    check("改动过内容就验签失败", out.get("kind") == "failed", str(out.get("kind")))
    check("错误里说明是校验问题", "校验" in str(out.get("msg", "")), str(out.get("msg")))

    print("\n== 内容不是 JSON / 不是清单 ==")
    out = run({}, "1.2.0")          # 没有 payload/signature
    check("缺字段的清单不认", out.get("kind") == "failed", str(out.get("kind")))
    checker = up.UpdateChecker()
    got = {}
    checker.failed.connect(lambda m: got.update(msg=m))
    checker._handle_bytes(b"<html>404</html>")
    app.processEvents()
    check("不是 JSON 时给中文提示", "JSON" in got.get("msg", ""), str(got.get("msg")))

    print("\n== 基线验证：真仓库那把公钥还在 ==")
    check("内置公钥是 64 位十六进制", len(manifest.PUBKEY_HEX) == 64)
    check("内置公钥没被测试改掉", manifest.PUBKEY_HEX != PUB)

    print("\n通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        for name in FAIL:
            print("  失败：" + name)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
