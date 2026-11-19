# -*- coding: utf-8 -*-
"""清单的「走 API」备用路：解析对不对、请求头对不对、找不到附件要报错。

为什么需要这条路：报障机器的环境里 github.com 主站整个不可达（实测 10 秒
超时、连 302 都发不出来），而 api.github.com 和 release-assets 还能用。
清单只能从 release 附件取（有签名），所以先用 API 找到 latest.json 的附件地址，
再用 Accept: application/octet-stream 让它 302 到 CDN。

这个测试不联网，把 urlopen 换掉，只看流程和请求头。

用法：
    python tools/test_manifest_api.py
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import update as up  # noqa: E402

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


class FakeResp(object):
    def __init__(self, payload):
        self._buf = io.BytesIO(payload)

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def install_fake(release_doc, asset_bytes):
    """把两次请求都拦下来，记录每次的 URL 和请求头。"""
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append((req.full_url, dict(req.header_items())))
        if req.full_url == up.LATEST_API:
            return FakeResp(json.dumps(release_doc).encode("utf-8"))
        return FakeResp(asset_bytes)

    up.urllib.request.urlopen = fake_urlopen
    return calls


_real_urlopen = up.urllib.request.urlopen

print("1) 正常：找到 latest.json 附件，并按附件地址取")
doc = {
    "tag_name": "v1.3.4",
    "assets": [
        {"name": "installer.exe", "url": "https://api.github.com/installer"},
        {"name": "latest.json", "url": "https://api.github.com/asset/latest"},
    ],
}
calls = install_fake(doc, b'{"version":"1.3.4"}')
try:
    data = up.fetch_manifest_via_api(6)
finally:
    up.urllib.request.urlopen = _real_urlopen
check("拿到了清单字节", data == b'{"version":"1.3.4"}', str(data))
check("一共两次请求", len(calls) == 2, str(len(calls)))
check("第一次打的是 latest API", calls and calls[0][0] == up.LATEST_API, str(calls[:1]))
check("第一次带 Accept: application/json 类头",
      any("accept" in k.lower() and "json" in v for k, v in calls[0][1].items()),
      str(calls[0][1]))
check("第二次打的是附件地址",
      len(calls) > 1 and calls[1][0] == "https://api.github.com/asset/latest",
      calls[1][0] if len(calls) > 1 else "")
check("第二次要的是二进制（会 302 到 CDN）",
      len(calls) > 1 and any("accept" in k.lower() and "octet-stream" in v
                             for k, v in calls[1][1].items()),
      str(calls[1][1] if len(calls) > 1 else {}))

print("2) 最新版本里没有 latest.json：要明确报错，不能拿空数据去验签")
install_fake({"tag_name": "v1.3.4", "assets": [{"name": "installer.exe",
                                               "url": "https://api.github.com/x"}]}, b"")
try:
    err = ""
    try:
        up.fetch_manifest_via_api(6)
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
finally:
    up.urllib.request.urlopen = _real_urlopen
check("给出可读的错误", "latest.json" in err, err)

print("3) 直连那条路仍然只打 github.com（能通时最快）")
seen = []


def fake_direct(req, timeout=None):
    seen.append((req.full_url, timeout))
    return FakeResp(b'{"version":"1.3.4"}')


up.urllib.request.urlopen = fake_direct
try:
    up.fetch_manifest_direct(3)
finally:
    up.urllib.request.urlopen = _real_urlopen
check("打的是原地址", seen and seen[0][0] == up.MANIFEST_URL, str(seen[:1]))
check("超时按传入值走", seen and seen[0][1] == 3, str(seen[:1]))

print()
if FAIL:
    print("失败 %d 项：%s" % (len(FAIL), "；".join(FAIL)))
    sys.exit(1)
print("全部通过（%d 项）" % len(PASS))
