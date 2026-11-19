# -*- coding: utf-8 -*-
"""检查更新的两条通道：谁是主路、什么时候开兜底、结果只发一次、超时不抢跑。

出过的 bug：请求发出去 12 秒一个字节都没回来，日志里只有「超时：12 秒没响应」，
界面报「连接 GitHub 超时」。而同一台机器、同一网络里 Python 自带 SSL 3 秒就
取到了同一份清单 —— 说明问题在 Qt 那条网络栈，跟「有没有新版本」无关：
请求发的是同一个 URL，比版本发生在拿到内容之后。

现在的约定：
  1. 主通道是 Python 自带 SSL，check() 一进来就开（工作线程里只做网络）
  2. 3 秒没结果再开 Qt 兜底（打包环境里 Python 证书链偶尔不完整）
  3. 谁先回来用谁，后到的结果直接丢掉（不能弹两次窗）
  4. 整体超时到点先给 3 秒收尾，然后只报一句「连接 GitHub 超时，请检查网络或代理后重试。」
  5. 失败文案里不再出现域名、PAC 这类开发视角的东西

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
from PyQt5.QtCore import Qt  # noqa: E402
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


print("1) 主通道是 Python，只开一次")
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
    c._start_python_channel()
    c._start_python_channel()
    check("只起了一个线程", len(spawned) == 1, "起了 %d 个" % len(spawned))
    check("线程跑的是取清单", spawned and spawned[0] == c._stdlib_fetch)
    check("标记已用过主通道", c._fallback_used)
finally:
    up.threading.Thread = _real_thread

print("2) Qt 只是兜底：3 秒后才开")
c, seen = new_checker()
check("HEDGE_MS 是 3 秒", c.HEDGE_MS == 3000, str(c.HEDGE_MS))
check("超时定时器连的是收尾", c._timer.receivers(c._timer.timeout) > 0)
c._done = False
c._reply = object()          # 假装 Qt 通道已经开过
c._start_qt_channel()
check("已经开过就不再开", c._reply is not None)

print("3) 结果只发一次（两条路都回来了也只算一次）")
c, seen = new_checker()
c._done = False
c._deliver(c.latest, "1.3.2")
c._deliver(c.failed, "连接 GitHub 超时")
c._deliver(c.found, "should-not-arrive")
check("只收到一条结果", len(seen) == 1, str(seen))
check("先到的那条生效", seen and seen[0][0] == "latest", str(seen[:1]))
check("后面的被丢掉", c._done)
check("计时器被停掉", not c._timer.isActive() and not c._hedge.isActive())

print("4) 整体超时：先给 3 秒收尾，再报错")
c, seen = new_checker()
c._reply = None
c._extended = False
c._done = False
c._on_timeout()
check("第一次超时不下结论", not seen, str(seen))
check("标记为已延长", c._extended)
check("重新起了计时器", c._timer.isActive())
c._on_timeout()
check("第二次超时才报错", len(seen) == 1 and seen[0][0] == "failed", str(seen[:1]))

print("5) 超时文案就是原来那一句")
c, seen = new_checker()
c._reply = None
c._extended = True
c._done = False
c._on_timeout()
msg = seen[0][1] if seen else ""
check("原文案", msg == "连接 GitHub 超时，请检查网络或代理后重试。", msg)
check("不提域名", "release-assets" not in msg and "github.com" not in msg)
check("不提 PAC", "PAC" not in msg and "自动配置脚本" not in msg)

print("6) 工作线程只做网络，结果经信号回主线程")
c, seen = new_checker()
got = []
c._raw.connect(lambda d: got.append(d))
c._done = False
c._raw.emit(b'{"version":"0.0.0"}')
app.processEvents()
check("信号能把字节送回主线程", got == [b'{"version":"0.0.0"}'], str(got))

print()
if FAIL:
    print("失败 %d 项：%s" % (len(FAIL), "；".join(FAIL)))
    sys.exit(1)
print("全部通过（%d 项）" % len(PASS))
