# -*- coding: utf-8 -*-
"""检查更新的两条通道：什么时候开第二条、结果只发一次、超时不抢跑。

出过的 bug：请求发出去 12 秒一个字节都没回来，日志里只有「超时：12 秒没响应」，
界面报「连接 GitHub 超时」。而同一条网络里 Python 自带 SSL 3 秒就取到了清单 ——
说明 Qt 那条腿在干等，另一条腿根本没被叫醒（以前只在 TLS 报错时才叫）。

现在的约定：
  1. 5 秒没结果就同时开第二条腿（只开一次）
  2. 谁先回来用谁，后到的结果直接丢掉（不能弹两次窗）
  3. 整体超时到点时，如果第二条腿还在跑，先别判死，再给 4 秒

用法：
    python tools/test_update_channels.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import qt_env  # noqa: E402

qt_env.setup()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import update as up  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def new_checker():
    c = up.UpdateChecker()
    seen = []
    c.found.connect(lambda i: seen.append(("found", i)))
    c.latest.connect(lambda v: seen.append(("latest", v)))
    c.failed.connect(lambda m: seen.append(("failed", m)))
    return c, seen


print("1) 第二条腿最多开一次")
c, seen = new_checker()
spawned = []


class _FakeThread(object):
    def __init__(self, target=None, daemon=None, **kw):
        spawned.append(target)

    def start(self):
        pass


_real_thread = up.threading.Thread
up.threading.Thread = _FakeThread
try:
    c._start_stdlib_channel()
    c._start_stdlib_channel()
    check("只起了一个线程", len(spawned) == 1, "起了 %d 个" % len(spawned))
    check("标记已用过备用通道", c._fallback_used)
finally:
    up.threading.Thread = _real_thread

print("2) 结果只发一次（两条腿都回来了也只算一次）")
c, seen = new_checker()
c._done = False
c._deliver(c.latest, "1.3.2")
c._deliver(c.failed, "连接 GitHub 超时")
c._deliver(c.found, "should-not-arrive")
check("只收到一条结果", len(seen) == 1, str(seen))
check("先到的那条生效", seen and seen[0][0] == "latest", str(seen[:1]))
check("后面的被丢掉", c._done)
check("计时器被停掉", not c._timer.isActive() and not c._hedge.isActive())

print("3) 整体超时：第二条腿还在跑就先别判死")
c, seen = new_checker()
c._reply = None
c._fallback_used = True
c._extended = False
c._done = False
up._pac_url = lambda: ""
c._on_timeout()
check("第一次超时不下结论", not seen, str(seen))
check("标记为已延长", c._extended)
check("重新起了计时器", c._timer.isActive())
c._on_timeout()
check("第二次超时才报错", len(seen) == 1 and seen[0][0] == "failed", str(seen[:1]))

print("4) 超时文案要说清该查什么")
c, seen = new_checker()
c._reply = None
c._fallback_used = True
c._extended = True
c._done = False
up._pac_url = lambda: ""
c._on_timeout()
msg = seen[0][1] if seen else ""
check("提到两个域名", "release-assets.githubusercontent.com" in msg, msg[:60])
check("提到代理", "代理" in msg)

print("5) 系统配了 PAC 时，直接指向 PAC 这个原因")
c, seen = new_checker()
c._reply = None
c._fallback_used = True
c._extended = True
c._done = False
up._pac_url = lambda: "http://127.0.0.1:7890/proxy.pac"
c._on_timeout()
msg = seen[0][1] if seen else ""
check("指出 PAC 是原因", "PAC" in msg or "自动配置脚本" in msg, msg[:70])
check("给出改法", "系统代理" in msg or "TUN" in msg)

print()
print("真实网络连通性（可选，看当前这台机器能不能直接取到清单）：")
print("  ", end="")
try:
    import urllib.request
    t0 = __import__("time").time()
    req = urllib.request.Request(up.MANIFEST_URL, headers={"User-Agent": up.USER_AGENT})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = r.read()
    print("Python 通道 %.1fs / %d 字节" % (__import__("time").time() - t0, len(data)))
except Exception as e:
    print("Python 通道失败：%s: %s" % (type(e).__name__, e))

print()
if FAIL:
    print("失败 %d 项：%s" % (len(FAIL), "；".join(FAIL)))
    sys.exit(1)
print("全部通过（%d 项）" % len(PASS))
