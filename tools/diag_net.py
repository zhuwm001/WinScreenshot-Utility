# -*- coding: utf-8 -*-
"""诊断「检查更新超时」卡在哪一步：DNS、连接、还是重定向。

对比三条路径，同一时刻跑一遍就看出差别：
  1. urllib 直连清单地址
  2. Qt 走系统代理（和程序里完全一样的取法）
  3. Qt 显式不走代理
另外打印系统代理配置和 DNS 解析结果，方便判断是不是代理没生效。
"""
import os
import socket
import sys
import time
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

import qt_env  # noqa: E402

qt_env.setup()

from PyQt5.QtCore import QTimer, QUrl  # noqa: E402
from PyQt5.QtNetwork import (QNetworkAccessManager, QNetworkProxy,  # noqa: E402
                             QNetworkProxyFactory, QNetworkRequest)
from PyQt5.QtWidgets import QApplication  # noqa: E402

from update import MANIFEST_URL, USER_AGENT  # noqa: E402

app = QApplication(sys.argv)


def probe_urllib():
    t0 = time.time()
    try:
        req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
        print("  urllib：%.2fs  HTTP %s  %d 字节  最终地址=%s"
              % (time.time() - t0, r.status, len(data), r.geturl()[:90]))
    except Exception as e:
        print("  urllib：%.2fs  失败 %s: %s" % (time.time() - t0, type(e).__name__, e))


def probe_qt(use_system_proxy: bool):
    nam = QNetworkAccessManager()
    if use_system_proxy:
        QNetworkProxyFactory.setUseSystemConfiguration(True)
    else:
        nam.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
    req = QNetworkRequest(QUrl(MANIFEST_URL))
    req.setHeader(QNetworkRequest.UserAgentHeader, USER_AGENT)
    req.setRawHeader(b"Cache-Control", b"no-cache")
    tried = {"n": 0, "t0": time.time()}
    reply = nam.get(req)

    def done():
        print("  Qt(%s)：%.2fs  error=%s  HTTP=%s  字节=%d  地址=%s"
              % ("系统代理" if use_system_proxy else "直连",
                 time.time() - tried["t0"],
                 reply.errorString(),
                 reply.attribute(QNetworkRequest.HttpStatusCodeAttribute),
                 len(reply.readAll()),
                 reply.url().toString()[:90]))

    reply.finished.connect(done)
    loop_timer = QTimer()
    loop_timer.setSingleShot(True)
    loop_timer.timeout.connect(lambda: (print("  Qt(%s)：12s 无响应（和日志里一样）"
                                              % ("系统代理" if use_system_proxy else "直连")),
                                     reply.abort()))
    loop_timer.start(12000)
    while reply.isRunning():
        app.processEvents()


print("清单地址：", MANIFEST_URL)
try:
    print("  DNS：", sorted({a[4][0] for a in socket.getaddrinfo("github.com", 443)}))
except Exception as e:
    print("  DNS 失败：", e)
try:
    proxies = QNetworkProxyFactory.systemProxyForQuery(
        __import__("PyQt5.QtNetwork", fromlist=["QNetworkProxyQuery"])
        .QNetworkProxyQuery(QUrl(MANIFEST_URL)))
    print("  系统代理：", [(p.type(), p.hostName(), p.port()) for p in proxies] or "无")
except Exception as e:
    print("  系统代理读取失败：", e)

print("\n1) Python 自带 SSL")
probe_urllib()
print("\n2) Qt 走系统代理（程序里的做法）")
probe_qt(True)
print("\n3) Qt 显式直连")
probe_qt(False)
