# -*- coding: utf-8 -*-
"""对比三种代理配置下，Qt 取同一份清单的耗时与结果。

用法：
    python tools/diag_proxy_modes.py <mode>
mode: noproxy | system | default

每个 mode 必须单独一个进程 —— setUseSystemConfiguration 是全局静态的，
同一进程里改不了，测出来也不可信。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PyQt5.QtCore import QCoreApplication, QTimer, QUrl          # noqa: E402
from PyQt5.QtNetwork import (QNetworkAccessManager, QNetworkProxy,  # noqa: E402
                             QNetworkProxyFactory, QNetworkRequest)

from update import MANIFEST_URL, USER_AGENT                      # noqa: E402

MODE = (sys.argv[1] if len(sys.argv) > 1 else "default").lower()

app = QCoreApplication(sys.argv)

nam = QNetworkAccessManager()

if MODE == "noproxy":
    nam.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
elif MODE == "system":
    QNetworkProxyFactory.setUseSystemConfiguration(True)
# default: 什么都不设，看 Qt 自己怎么选

req = QNetworkRequest(QUrl(MANIFEST_URL))
req.setHeader(QNetworkRequest.UserAgentHeader, USER_AGENT)
req.setRawHeader(b"Cache-Control", b"no-cache")

t0 = time.monotonic()


def done():
    ms = (time.monotonic() - t0) * 1000
    p = nam.proxy()                     # 实际生效的代理；空 host 表示直连
    print("%-8s %7.0f ms  err=%s  status=%s  bytes=%s  proxy=%s:%d"
          % (MODE, ms,
             reply.error(),
             reply.attribute(QNetworkRequest.HttpStatusCodeAttribute),
             reply.bytesAvailable(),
             p.hostName() or "直连",
             p.port()))
    app.quit()


reply = nam.get(req)
reply.finished.connect(done)

QTimer.singleShot(15000, lambda: (print("%-8s 15000 ms 仍未完成" % MODE), app.quit()))
sys.exit(app.exec_())
