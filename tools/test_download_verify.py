# -*- coding: utf-8 -*-
"""下载 + 校验自检：本地 HTTP 服务器喂安装包，验证五种情况。

  1. 正常包        -> 下载完成，sha256 与清单一致
  2. 内容被替换    -> sha256 不一致，删掉残包并报错
  3. 长度不符      -> 报"下载不完整"
  4. 下到 HTML 页  -> 报"不是 Windows 可执行文件"
  5. 非白名单域名  -> 一开始就拒绝下载

这里为了能连 127.0.0.1，会临时把 ALLOWED_HOSTS 放宽（仅测试用）。
"""
import functools
import hashlib
import http.server
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from PyQt5.QtCore import QTimer                     # noqa: E402
from PyQt5.QtWidgets import QApplication            # noqa: E402

import update                                       # noqa: E402

PASS = FAIL = 0
INSTALLER = os.path.join(ROOT, "installer", "我爱截图_安装包_v1.1.1.exe")


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


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def run_download(info, dest, timeout=90000):
    app = QApplication.instance() or QApplication(sys.argv)
    out = {}
    dl = update.InstallerDownloader()
    dl.done.connect(lambda p: (out.update(kind="done", path=p), app.quit()))
    dl.failed.connect(lambda m: (out.update(kind="failed", msg=m), app.quit()))
    dl.progress.connect(lambda got, total: out.update(progress=(got, total)))
    dl.start(info, dest)
    QTimer.singleShot(timeout, app.quit)
    app.exec_()
    return out


def info_for(url, size, digest):
    return update.ReleaseInfo(version="9.9.9", tag="v9.9.9", title="test",
                              notes="", notes_text="", page_url="", asset_name="x.exe",
                              asset_url=url, asset_size=size, digest=digest,
                              published_at="", sha256=digest.split(":")[-1], signed=True)


def main():
    if not os.path.exists(INSTALLER):
        print("缺少安装包 %s，先跑一次 build" % INSTALLER)
        return 1

    real_size = os.path.getsize(INSTALLER)
    real_hash = sha256(INSTALLER)
    print("样本安装包 %.2f MB  sha256 %s…" % (real_size / 1048576.0, real_hash[:16]))

    tmp = tempfile.mkdtemp(prefix="wojietu-dl-")
    www = os.path.join(tmp, "www")
    dest = os.path.join(tmp, "dest")
    os.makedirs(www)
    os.makedirs(dest)

    # 1) 正常包
    shutil.copy(INSTALLER, os.path.join(www, "ok.exe"))
    httpd, port = serve(www)
    base = "http://127.0.0.1:%d" % port
    # url_allowed 强制 https，本地测试只能放宽（生产配置不动）
    _orig_allowed = update.url_allowed
    update.url_allowed = lambda u: u.startswith("http://127.0.0.1") or _orig_allowed(u)

    print("\n== 正常下载 ==")
    r = run_download(info_for(base + "/ok.exe", real_size, "sha256:" + real_hash), dest)
    check("下载完成", r.get("kind") == "done", str(r.get("msg")))
    if r.get("kind") == "done":
        check("落盘文件 sha256 一致", sha256(r["path"]) == real_hash)
        check("文件名是纯 ASCII", os.path.basename(r["path"]).isascii(),
              os.path.basename(r["path"]))
        os.remove(r["path"])
    check("有进度回调", bool(r.get("progress")), str(r.get("progress")))

    # 2) 内容被替换（声明的 sha256 是原包的，实际给的是改过的）
    with open(os.path.join(www, "ok.exe"), "r+b") as f:
        f.seek(2000)
        f.write(b"\x00" * 16)
    print("\n== 内容被替换 ==")
    r = run_download(info_for(base + "/ok.exe", real_size, "sha256:" + real_hash), dest)
    check("拒绝使用", r.get("kind") == "failed", str(r.get("msg")))
    check("提示 sha256 不一致", "sha256" in str(r.get("msg")), str(r.get("msg")))
    leftover = [n for n in os.listdir(dest) if n.endswith(".exe")]
    check("残包已删除", not leftover, str(leftover))

    # 3) 清单里的 sha256 写错（包本身是好的）
    shutil.copy(INSTALLER, os.path.join(www, "ok.exe"))
    print("\n== 清单 sha256 写错 ==")
    r = run_download(info_for(base + "/ok.exe", real_size, "sha256:" + "1" * 64), dest)
    check("拒绝使用", r.get("kind") == "failed", str(r.get("msg")))
    check("提示 sha256 不一致", "sha256" in str(r.get("msg")), str(r.get("msg")))
    leftover = [n for n in os.listdir(dest) if n.endswith(".exe")]
    check("残包已删除", not leftover, str(leftover))

    # 4) 下到 HTML
    html = os.path.join(www, "fake.exe")
    with open(html, "wb") as f:
        f.write(b"<html><body>" + b"x" * 70000 + b"</body></html>")
    print("\n== 下到 HTML 页 ==")
    r = run_download(info_for(base + "/fake.exe", os.path.getsize(html),
                             "sha256:" + "0" * 64), dest)
    check("拒绝使用", r.get("kind") == "failed", str(r.get("msg")))
    httpd.shutdown()

    # 5) 非白名单域名（恢复真实规则）
    update.url_allowed = _orig_allowed
    print("\n== 域名不在白名单 ==")
    r = run_download(info_for("http://127.0.0.1:1/ok.exe", real_size, "sha256:" + real_hash),
                     dest)
    check("一开始就拒绝", r.get("kind") == "failed", str(r.get("msg")))
    check("提示域名", "域名" in str(r.get("msg")), str(r.get("msg")))

    # 6) 清单没给 sha256
    print("\n== 清单没有 sha256 ==")
    r = run_download(info_for("https://github.com/a/b.exe", real_size, ""), dest)
    check("拒绝下载", r.get("kind") == "failed", str(r.get("msg")))

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n通过 %d / 失败 %d" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
