# -*- coding: utf-8 -*-
"""更新检查的端到端自检：用本地 HTTP 服务器喂清单，验证四种结果。

覆盖：
  1. 真清单（取自线上 Release）      -> 报「发现新版本」
  2. 篡改 sha256 的清单              -> 拒绝，提示签名校验失败
  3. 换把钥匙签的清单                -> 拒绝
  4. 服务器上没有清单（404）          -> 给 404 的友好提示

注意：这里只替换 MANIFEST_URL，其余走真实 UpdateChecker / Qt 网络栈。
"""
import functools
import http.server
import io
import json
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import qt_env  # noqa: E402  Qt 平台插件路径统一处理，避免弹 no Qt platform plugin
qt_env.setup()

from PyQt5.QtCore import QTimer                     # noqa: E402
from PyQt5.QtWidgets import QApplication            # noqa: E402

import ed25519                                      # noqa: E402
import manifest                                     # noqa: E402
import update                                       # noqa: E402

PASS = FAIL = 0
SAMPLE = os.path.join(HERE, "latest.manifest.sample.json")     # 提交进仓库的线上清单快照
FALLBACK = os.path.join(ROOT, "build", "_man.json")           # 快照缺失时从线上抓


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  [ok]   %s%s" % (name, ("  " + detail) if detail else ""))
    else:
        FAIL += 1
        print("  [FAIL] %s%s" % (name, ("  " + detail) if detail else ""))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(directory):
    handler = functools.partial(Quiet, directory=directory)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def run_check(current, timeout=8000):
    app = QApplication.instance() or QApplication(sys.argv)
    out = {}
    checker = update.UpdateChecker()
    checker.found.connect(lambda i: (out.update(kind="found", info=i), app.quit()))
    checker.latest.connect(lambda v: (out.update(kind="latest", ver=v), app.quit()))
    checker.failed.connect(lambda m: (out.update(kind="failed", msg=m), app.quit()))
    checker.check(current, timeout_ms=timeout)
    QTimer.singleShot(timeout + 2000, app.quit)
    app.exec_()
    return out


def main():
    sample = SAMPLE
    if not os.path.exists(sample):
        import urllib.request
        print("仓库里没有清单快照，从线上取一份…")
        os.makedirs(os.path.dirname(FALLBACK), exist_ok=True)
        with urllib.request.urlopen(update.MANIFEST_URL, timeout=30) as r:
            data = r.read()
        with open(FALLBACK, "wb") as f:
            f.write(data)
        sample = FALLBACK
    raw = json.load(io.open(sample, encoding="utf-8"))
    payload, reason = manifest.verify_document(raw)
    if payload is None:
        print("样本清单本身验签不过：%s" % reason)
        return 1
    print("样本清单：%s  %s" % (payload["version"], payload["asset"]["name"]))

    tmp = tempfile.mkdtemp(prefix="wojietu-man-")

    # 1) 正常清单
    d1 = os.path.join(tmp, "good")
    os.makedirs(d1)
    shutil.copy(sample, os.path.join(d1, "latest.json"))
    httpd, port = serve(d1)
    update.MANIFEST_URL = "http://127.0.0.1:%d/latest.json" % port
    print("\n== 正常清单 ==")
    r = run_check("1.0.1")
    check("发现新版本", r.get("kind") == "found",
          "%s  %s" % (r.get("info").version, r.get("info").size_text)
          if r.get("kind") == "found" else str(r.get("msg")))
    check("标记为已签名", bool(r.get("kind") == "found" and r["info"].signed))
    check("sha256 已带入", bool(r.get("kind") == "found"
                              and r["info"].digest.startswith("sha256:")))
    r2 = run_check(payload["version"])
    check("同版本报已是最新", r2.get("kind") == "latest", str(r2.get("ver")))
    httpd.shutdown()

    # 2) 篡改 sha256
    d2 = os.path.join(tmp, "tampered")
    os.makedirs(d2)
    bad = json.loads(json.dumps(raw))
    bad["payload"]["asset"]["sha256"] = "0" * 64
    io.open(os.path.join(d2, "latest.json"), "w", encoding="utf-8").write(
        json.dumps(bad, ensure_ascii=False))
    httpd, port = serve(d2)
    update.MANIFEST_URL = "http://127.0.0.1:%d/latest.json" % port
    print("\n== 篡改 sha256 ==")
    r = run_check("1.0.1")
    check("拒绝安装", r.get("kind") == "failed", str(r.get("msg")))
    check("提示是签名问题", "签名" in str(r.get("msg")), str(r.get("msg")))
    httpd.shutdown()

    # 3) 别人拿自己的钥匙签
    d3 = os.path.join(tmp, "forged")
    os.makedirs(d3)
    seeded = manifest.build(payload, os.urandom(32))
    io.open(os.path.join(d3, "latest.json"), "w", encoding="utf-8").write(
        json.dumps(seeded, ensure_ascii=False))
    httpd, port = serve(d3)
    update.MANIFEST_URL = "http://127.0.0.1:%d/latest.json" % port
    print("\n== 伪造签名 ==")
    r = run_check("1.0.1")
    check("拒绝安装", r.get("kind") == "failed", str(r.get("msg")))
    httpd.shutdown()

    # 4) 服务器上没有清单
    d4 = os.path.join(tmp, "empty")
    os.makedirs(d4)
    httpd, port = serve(d4)
    update.MANIFEST_URL = "http://127.0.0.1:%d/latest.json" % port
    print("\n== 没有清单（404）==")
    r = run_check("1.0.1")
    check("给出 404 提示", r.get("kind") == "failed" and "404" in str(r.get("msg")),
          str(r.get("msg")))
    httpd.shutdown()

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n通过 %d / 失败 %d" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
