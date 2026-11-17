# -*- coding: utf-8 -*-
"""联网实测一次「检查更新」的整条链路（清单下载 + 验签 + 版本比较）。

需要在能访问 GitHub 的机器上手动跑，所以不放进常规自检：
    python tools/test_update_live.py

三种情况各跑一遍：
    1. 本地假装是 1.0.0 -> 应该「发现新版本」
    2. 本地就是当前版本 -> 应该「已是最新」
    3. 断网/改坏地址 -> 应该给出人话版错误，而不是卡住不动
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def _preload_openssl():
    """源码里跑时先把 OpenSSL 两个库载进进程。

    Qt 只会到"程序所在目录"找 libssl / libcrypto，而源码运行的程序目录是
    python.exe 所在的目录，那里没有这两个库 —— 直接跑会报 TLS initialization
    failed（打好的安装包里 build_exe.py 会把它们复制到 exe 旁边，所以没这问题）。
    这里显式载入一次，Windows 会把同名模块直接复用。
    """
    if getattr(sys, "frozen", False):
        return
    try:
        import PyQt5
        qt_bin = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "bin")
    except Exception:
        return
    try:
        os.add_dll_directory(qt_bin)
    except (AttributeError, OSError):
        pass
    import ctypes
    for name in ("libcrypto-1_1-x64.dll", "libssl-1_1-x64.dll"):
        path = os.path.join(qt_bin, name)
        if os.path.exists(path):
            try:
                ctypes.WinDLL(path)
            except OSError:
                pass


_preload_openssl()

from PyQt5.QtCore import QTimer                            # noqa: E402
from PyQt5.QtWidgets import QApplication                   # noqa: E402

import update as up                                        # noqa: E402
from app_config import APP_VERSION                         # noqa: E402

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def run_check(current, timeout_ms=20000):
    """跑一次 UpdateChecker，返回 ('found'|'latest'|'failed', 负载)。"""
    app = QApplication.instance() or QApplication(sys.argv)
    result = {}
    done = {"v": False}

    checker = up.UpdateChecker()
    checker.found.connect(lambda info: (result.update(kind="found", info=info),
                                        done.__setitem__("v", True)))
    checker.latest.connect(lambda ver: (result.update(kind="latest", ver=ver),
                                        done.__setitem__("v", True)))
    checker.failed.connect(lambda msg: (result.update(kind="failed", msg=msg),
                                        done.__setitem__("v", True)))
    checker.check(current, timeout_ms=timeout_ms)

    end = time.time() + timeout_ms / 1000.0 + 2
    while time.time() < end and not done["v"]:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    return result if done["v"] else {"kind": "timeout"}


def fetch_with_urllib(url, timeout=20):
    """不经过 Qt 直接抓一遍清单。

    源码运行时 Qt 可能因为找不到 OpenSSL 报 TLS 失败（打好的安装包不受影响），
    这时用系统自带的 TLS 抓同一份文件，把验签 / 版本比较这些真正的逻辑测掉。
    """
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "WoAiJieTu-Updater/1.0",
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main():
    print("联网检查更新实测（当前版本 %s）" % APP_VERSION)

    print("\n== 假装本地是 1.0.0 ==")
    r = run_check("1.0.0")
    tls_broken = r.get("kind") == "failed" and "加密连接" in str(r.get("msg", ""))
    if tls_broken:
        print("     注意：源码环境缺 OpenSSL（安装包里 build_exe.py 会把库拷到 exe 旁边），")
        print("     这一轮改用系统 TLS 抓清单，验签与版本比较照样测。")
    else:
        check("确实发现了新版本", r.get("kind") == "found", str(r.get("kind")))
        if r.get("kind") == "found":
            info = r["info"]
            check("版本号比 1.0.0 大", up.is_newer(info.version, "1.0.0"), info.version)
            check("清单是签过名的", bool(getattr(info, "signed", False)))
            check("带 sha256 校验值", bool(info.sha256), info.sha256[:16] + "…")
            check("有安装包下载地址", bool(info.asset_url), str(info.asset_url)[:60])
            check("安装包地址在允许的域名下", up.url_allowed(info.asset_url or ""))
            check("有更新说明", bool(info.notes_text.strip()))
            print("     远端最新版本：%s" % info.version)

    print("\n== 远端清单本身（验签 + 版本比较） ==")
    try:
        raw = fetch_with_urllib(up.MANIFEST_URL)
        check("清单能下载到", bool(raw), "%d 字节" % len(raw))
        import json
        doc = json.loads(raw.decode("utf-8", "replace"))
        payload, reason = up.manifest.verify_document(doc)
        check("签名校验通过", payload is not None, "" if payload else str(reason))
        if payload is not None:
            ver = ".".join(str(x) for x in up.parse_version(payload.get("version")))
            print("     远端版本：%s" % ver)
            newer = up.parse_manifest(payload, "1.0.0")
            check("比 1.0.0 新时能认出来", newer is not None and newer.signed)
            check("比远端同版本时不认", up.parse_manifest(payload, ver) is None)
            if newer is not None:
                check("sha256 已带进安装信息", bool(newer.digest.startswith("sha256:")))
                check("下载地址在允许域名下", up.url_allowed(newer.asset_url or ""))
    except Exception as e:
        check("清单能下载到", False, "%s: %s" % (type(e).__name__, e))

    print("\n== 拿当前版本去比 ==")
    r2 = run_check(APP_VERSION)
    if r2.get("kind") == "failed" and "加密连接" in str(r2.get("msg", "")):
        print("     跳过（源码环境 TLS 不可用，见上）")
    else:
        check("应判定为已是最新", r2.get("kind") == "latest", str(r2.get("kind")))

    print("\n== 地址坏掉时要说人话 ==")
    old = up.MANIFEST_URL
    up.MANIFEST_URL = "https://github.com/zhuwm001/WinScreenshot-Utility/releases/latest/download/nope.json"
    try:
        r3 = run_check(APP_VERSION, timeout_ms=15000)
    finally:
        up.MANIFEST_URL = old
    check("失败而不是卡死", r3.get("kind") == "failed", str(r3.get("kind")))
    check("错误信息有中文提示", "HTTP" in str(r3.get("msg", "")) or
          "超时" in str(r3.get("msg", "")), str(r3.get("msg")))

    print("\n通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        for name in FAIL:
            print("  失败：" + name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
