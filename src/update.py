# -*- coding: utf-8 -*-
"""检查更新：GitHub Release -> 下载安装包 -> 静默安装并重启。

三步走：
  1. UpdateChecker       请求 releases/latest，和本地版本比大小
  2. InstallerDownloader 把 exe 下到临时目录，顺带校验大小 / sha256
  3. launch_silent_install 延时启动 Inno Setup 静默安装，装完再拉起新版本

前提：仓库必须是**公开**的。私有仓库的 Release 匿名读不到（GitHub 返回 404），
别人电脑上的更新检查就永远失败 —— 可以在环境变量 WOJIETU_GITHUB_TOKEN 里塞一个
只读令牌绕过，但令牌会随 exe 分发出去，不安全，不建议。
"""
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from PyQt5.QtCore import QFile, QIODevice, QObject, QTimer, QUrl, pyqtSignal
from PyQt5.QtNetwork import (
    QNetworkAccessManager, QNetworkProxyFactory, QNetworkRequest,
)

from app_config import APP_NAME, APP_VERSION
import manifest
from update_log import log as ulog

# ---------------------------------------------------------------- 常量
# 只改这一行就能换仓库
REPO = "tiamma46/WinScreenshot-Utility"
API_ROOT = "https://api.github.com"
LATEST_API = "%s/repos/%s/releases/latest" % (API_ROOT, REPO)
# 永远指向「最新那个 Release」上的同名附件，不用先查 API 拿 id
MANIFEST_URL = "https://github.com/%s/releases/latest/download/latest.json" % REPO
RELEASE_PAGE = "https://github.com/%s/releases/latest" % REPO
USER_AGENT = "WoAiJieTu-Updater/1.0"

# 安装包只许从这几个域名下，防止清单被改指到奇怪的地方（清单本身有签名，这里是第二道）
ALLOWED_HOSTS = (
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "github-releases.githubusercontent.com",
)


# ---------------------------------------------------------------- 版本号
_NUM_RE = re.compile(r"(\d+(?:\.\d+)*)")


def parse_version(text):
    """'v1.0.2' / '1.0.2-beta1' / (1,0,2) -> (1, 0, 2)，认不出来就返回空元组。"""
    if isinstance(text, (tuple, list)):
        parts = [int(x) for x in text]
    else:
        m = _NUM_RE.search(str(text or ""))
        if not m:
            return ()
        parts = [int(x) for x in m.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(remote, local) -> bool:
    """远端版本是否比本地新。解析失败一律当"不新"，避免误报。"""
    r, l = parse_version(remote), parse_version(local)
    if not r or not l:
        return False
    return r > l


# ---------------------------------------------------------------- 结构化信息
class ReleaseInfo(object):
    """一条 Release 里更新程序需要的那几样东西。"""

    __slots__ = ("version", "tag", "title", "notes", "notes_text", "page_url",
                 "asset_name", "asset_url", "asset_size", "digest", "published_at",
                 "sha256", "signed")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    @property
    def has_installer(self) -> bool:
        return bool(self.asset_url)

    @property
    def size_text(self) -> str:
        size = self.asset_size or 0
        if size <= 0:
            return ""
        if size >= 1024 * 1024:
            return "%.1f MB" % (size / 1024.0 / 1024.0)
        return "%.0f KB" % (size / 1024.0)

    def __repr__(self):
        return "<ReleaseInfo %s %s>" % (self.version, self.asset_name)


def pick_installer_asset(assets):
    """从附件里挑安装包：优先名字带「安装包 / setup / installer」的 exe。"""
    assets = assets or []
    exes = [a for a in assets
            if str(a.get("name", "")).lower().endswith(".exe")]
    if not exes:
        return None
    for a in exes:
        name = str(a.get("name", "")).lower()
        if "安装包" in name or "setup" in name or "installer" in name:
            return a
    return exes[0]


def plain_notes(body, limit=4000) -> str:
    """把 Release 正文的 Markdown 揉成能直接看的大白话（保留列表和标题文字）。"""
    out = []
    for raw in str(body or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            out.append("")
            continue
        if line.startswith("<!--") or line.startswith("**Full Changelog**"):
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)              # 标题去掉井号
        line = re.sub(r"^\s*[-*+]\s+", "· ", line)          # 列表符换成小圆点
        line = line.replace("**", "").replace("__", "")
        # 去掉句尾的提交号：GitHub 自动生成的日志里会长这样
        #   ... 修复黑屏 (#12) (a1b2c3d)   /   ... in https://github.com/.../pull/12
        line = re.sub(r"\s*\((?:\[[0-9a-f]{6,}\]\([^)]*\)|[0-9a-f]{7,})\)\s*$", "",
                      line, flags=re.IGNORECASE)
        line = re.sub(r"\s+in\s+https?://\S+$", "", line, flags=re.IGNORECASE)
        out.append(line)
    text = "\n".join(out).strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    if len(text) > limit:
        text = text[:limit].rstrip() + "\n…"
    return text


def parse_release(data, current=APP_VERSION, allow_same=False):
    """把 API 返回的 JSON 变成 ReleaseInfo；不比本地新就返回 None。"""
    if not isinstance(data, dict):
        return None
    tag = data.get("tag_name") or data.get("name") or ""
    version = parse_version(tag)
    if not version:
        return None
    if not allow_same and not is_newer(version, current):
        return None

    asset = pick_installer_asset(data.get("assets"))
    body = data.get("body") or ""
    return ReleaseInfo(
        version=".".join(str(x) for x in version),
        tag=tag,
        title=data.get("name") or tag,
        notes=body,
        notes_text=plain_notes(body),
        page_url=data.get("html_url") or RELEASE_PAGE,
        asset_name=(asset or {}).get("name"),
        asset_url=(asset or {}).get("browser_download_url"),
        asset_size=(asset or {}).get("size") or 0,
        digest=(asset or {}).get("digest") or "",
        published_at=data.get("published_at") or "",
        sha256="",
        signed=False,          # 走 API 的这条路没有签名，只留作兼容
    )


def parse_manifest(payload, current=APP_VERSION):
    """把验签通过的清单 payload 变成 ReleaseInfo；不比本地新就返回 None。"""
    if not isinstance(payload, dict):
        return None
    version = ".".join(str(x) for x in parse_version(payload.get("version")))
    if not version or not is_newer(version, current):
        return None
    asset = payload.get("asset") or {}
    sha = str(asset.get("sha256") or "").lower()
    notes = payload.get("notes") or ""
    return ReleaseInfo(
        version=version,
        tag=str(payload.get("tag") or ""),
        title="%s %s" % (APP_NAME, version),
        notes=notes,
        notes_text=plain_notes(notes),
        page_url=RELEASE_PAGE,
        asset_name=asset.get("name"),
        asset_url=asset.get("url"),
        asset_size=int(asset.get("size") or 0),
        digest=("sha256:" + sha) if sha else "",
        published_at=payload.get("published_at") or "",
        sha256=sha,
        signed=True,
    )


def url_allowed(url: str) -> bool:
    """安装包地址是不是在允许的域名下。"""
    try:
        from urllib.parse import urlparse
        u = urlparse(url)
    except Exception:
        return False
    if u.scheme != "https":
        return False
    host = (u.hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


# ---------------------------------------------------------------- 路径
def running_exe() -> str:
    """当前运行的可执行文件路径（源码运行时是脚本本身）。"""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(sys.argv[0])


def update_dir() -> str:
    """存安装包和状态文件的目录。

    不用 %TEMP%：那是系统清理工具、磁盘清理和部分杀软最爱扫的地方，
    安装包在里面可能没等安装就被删掉/隔离，且不同用户/会话还可能变。
    %LOCALAPPDATA%\\我爱截图\\update 跟着用户走，稳定可写。
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME, "update")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        return tempfile.gettempdir()
    return d


def comspec() -> str:
    """cmd.exe 的绝对路径。

    COMSPEC 被改坏或没继承到的环境是存在的（某些启动器、精简版系统），
    所以再兜一层 SystemRoot，最后才退回 PATH 里的 cmd.exe。
    """
    cands = [os.environ.get("COMSPEC") or "",
             os.path.join(os.environ.get("SystemRoot") or r"C:\Windows",
                          "System32", "cmd.exe"),
             os.path.join(os.environ.get("windir") or r"C:\Windows",
                          "System32", "cmd.exe")]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return "cmd.exe"


def install_dir_writable(target_exe: str = "") -> bool:
    """安装目录当前用户能不能直接写。

    写不进去就别指望静默安装（它会一声不响地失败），改成带界面的安装，
    至少用户能看到错误或自己处理。
    """
    exe = target_exe or running_exe()
    folder = os.path.dirname(os.path.abspath(exe))
    probe = os.path.join(folder, ".wojietu-write-probe")
    try:
        with open(probe, "wb") as f:
            f.write(b"1")
        os.remove(probe)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 安装回执
# 装之前落一个 pending.json，新版本第一次起来时据此判断「上次更新到底成没成」，
# 再也不需要用户自己猜、也不需要日志。
def pending_path() -> str:
    return os.path.join(update_dir(), "pending.json")


def write_pending(version: str, installer: str) -> str:
    path = pending_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": version or "", "installer": installer or ""},
                      f, ensure_ascii=False)
    except Exception:
        return ""
    return path


def read_pending() -> dict:
    try:
        with open(pending_path(), "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def clear_pending():
    try:
        os.remove(pending_path())
    except Exception:
        pass


def version_from_installer(path: str) -> str:
    """从下载的文件名里取版本号（wojietu-setup-1.1.6.exe -> 1.1.6）。"""
    m = re.search(r"wojietu-setup-(.+)\.exe$", os.path.basename(path or ""),
                  re.IGNORECASE)
    return m.group(1) if m else ""


def cleanup_installers(keep: str = ""):
    """删掉残留的旧安装包（一个 30MB 压在盘里没必要）。"""
    folder = update_dir()
    keep = os.path.basename(keep or "").lower()
    try:
        for name in os.listdir(folder):
            low = name.lower()
            if not (low.startswith("wojietu-setup-") and low.endswith(".exe")):
                continue
            if keep and low == keep:
                continue
            try:
                os.remove(os.path.join(folder, name))
            except Exception:
                pass
    except Exception:
        pass


# ---------------------------------------------------------------- 网络
def _token() -> str:
    return (os.environ.get("WOJIETU_GITHUB_TOKEN") or "").strip()


def fetch_manifest_direct(timeout: float) -> bytes:
    """原路：github.com 上的 latest 直链。一次请求，能通就最快。"""
    req = urllib.request.Request(
        MANIFEST_URL,
        headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_manifest_via_api(timeout: float) -> bytes:
    """备用路：先问 API 要「最新版本」，再按附件地址把 latest.json 取下来。

    为什么需要这一条：国内直连时 `github.com` 主站经常整个不可达 —— 连 302
    都发不出来，请求就干等；而 `api.github.com` 和 `release-assets` 这两个域名
    往往还能用（安装包能下载、检查更新却超时，就是这种组合）。

    清单只能从 release 附件里取（它有签名），不能换成 API 的 release JSON。
    API 返回的 `assets[].url` 带上 `Accept: application/octet-stream` 会 302
    到 CDN 域名，正好绕开打不开的主站。内容一模一样，验签照常。
    """
    req = urllib.request.Request(
        LATEST_API,
        headers={"User-Agent": USER_AGENT,
                 "Accept": "application/vnd.github+json",
                 "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        release = json.loads(resp.read().decode("utf-8", "replace"))

    item = None
    for asset in (release.get("assets") or []):
        if str(asset.get("name") or "") == "latest.json":
            item = asset
            break
    if item is None or not item.get("url"):
        raise RuntimeError("最新版本里没有 latest.json 附件")

    req2 = urllib.request.Request(
        str(item["url"]),
        headers={"User-Agent": USER_AGENT,
                 "Accept": "application/octet-stream"})
    with urllib.request.urlopen(req2, timeout=timeout) as resp:
        return resp.read()


def _pac_url() -> str:
    """系统「自动配置脚本（PAC）」的地址；没设置就返回空串。

    不少代理软件勾了「自动配置系统代理」之后，写进系统的其实是一个 PAC 脚本。
    Qt 的网络栈**不支持 PAC**，遇到这种配置会当成直连，于是在必须走代理的网络里
    表现成"请求发出去，一个字节都没回来"。单独把它读出来，超时的时候这句就能
    直接告诉用户该改哪里，而不是让他去猜"网络还是代理"。
    """
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        try:
            value, _ = winreg.QueryValueEx(key, "AutoConfigURL")
        finally:
            key.Close()
        return str(value or "").strip()
    except Exception:
        return ""


def _make_nam(parent=None) -> QNetworkAccessManager:
    nam = QNetworkAccessManager(parent)
    try:
        # 走系统代理：公司网络 / 代理软件都能用，不用自己配
        QNetworkProxyFactory.setUseSystemConfiguration(True)
    except Exception:
        pass
    try:
        nam.setRedirectPolicy(QNetworkRequest.NoLessSafeRedirectPolicy)
    except Exception:
        try:
            nam.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        except Exception:
            pass
    return nam


def _request(url: str) -> QNetworkRequest:
    req = QNetworkRequest(QUrl(url))
    req.setHeader(QNetworkRequest.UserAgentHeader, USER_AGENT)
    # 只有真的打 API 时才带那套头；附件下载（github.com/...）带了反而多余
    if "api.github.com" in url:
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setRawHeader(b"X-GitHub-Api-Version", b"2022-11-28")
    req.setRawHeader(b"Cache-Control", b"no-cache")
    tok = _token()
    if tok:
        req.setRawHeader(b"Authorization", ("Bearer " + tok).encode("ascii"))
    return req


def _http_hint(status: int) -> str:
    if status == 404:
        return ("未找到更新清单（HTTP 404）。可能尚未发布包含 latest.json 的版本，"
                "或仓库已改为私有。")
    if status in (403, 429):
        return "GitHub 拒绝访问（HTTP %d），请求可能过于频繁，请稍后重试。" % status
    if status >= 500:
        return "GitHub 服务器暂时不可用（HTTP %d），请稍后重试。" % status
    return "GitHub 返回 HTTP %d。" % status


def _network_error(detail: str) -> str:
    """把 Qt / urllib 的英文错误翻成中文；TLS 那条最容易让人误以为网络中断。"""
    detail = detail or "未知错误"
    low = detail.lower()
    if "tls initialization" in low or "ssl handshake" in low:
        return ("无法建立加密连接（%s）。请确认系统时间正确、网络可访问 GitHub；"
                "如使用代理，请确认代理支持 HTTPS。" % detail)
    if "tunnel connection failed" in low or "proxyerror" in low or "proxy" in low:
        return ("代理服务器无法连接 GitHub（%s）。请确认代理软件正常运行，"
                "或暂时关闭代理后重试。" % detail)
    m = re.search(r"http error (\d{3})", low)
    if m:
        return _http_hint(int(m.group(1)))
    if "timed out" in low or "timeout" in low:
        return "连接 GitHub 超时，请检查网络或代理后重试。"
    if "host not found" in low or "unknown error" in low or "getaddrinfo" in low:
        return "无法解析 GitHub 域名（DNS 失败），请检查网络或代理设置。"
    if "connection refused" in low or "connection closed" in low:
        return "连接被中断（%s），可能被代理或防火墙拦截。" % detail
    return "网络连接失败：%s" % detail


def _is_tls_error(detail: str) -> bool:
    low = (detail or "").lower()
    return "tls initialization" in low or "ssl handshake" in low


class UpdateChecker(QObject):
    """异步检查一次最新版本。三种结果三选一，不会都发。

    只认**签过名**的清单（latest.json）：拿不到或验签不过一律失败，
    绝不退回去用未签名的数据。

    主通道是 Python 自带的 SSL，不是 Qt。原因是报障现场反复出现同一种形态：
    请求发出去，12 秒里一个字节都没回来、连错误回调都没有，而同一时刻同一网络
    下 Python 通道 3 秒就能拿到同一份清单。这是 Qt 网络栈在个别机器上的问题
    （连接复用、DNS 缓存、系统代理残留都可能），跟"有没有新版本"没有关系 ——
    请求发的是同一个 URL，版本比较发生在拿到内容之后。

    Qt 仍然保留成兜底：打包环境里 Python 的证书链偶尔不完整，而 Qt 自带的
    OpenSSL 是随包发出的。主通道 3 秒不回就同时开跑，谁先回来用谁的，只发一次结果。
    """

    found = pyqtSignal(object)     # ReleaseInfo
    latest = pyqtSignal(str)       # 当前版本，已是最新
    failed = pyqtSignal(str)       # 人话版错误
    # 工作线程拿到的原始字节交回主线程处理：定时器和网络对象都只属于主线程
    _raw = pyqtSignal(object)

    # 主通道 3 秒还没结果就同时开 Qt 兜底：正常网络 1–3 秒就回来了，
    # 等到 3 秒基本可以断定这条腿在干等。
    HEDGE_MS = 3000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = _make_nam(self)
        self._reply = None
        self._done = False
        self._current = APP_VERSION
        self._fallback_used = False
        self._extended = False
        self._timeout_s = 10
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._hedge = QTimer(self)
        self._hedge.setSingleShot(True)
        self._hedge.timeout.connect(self._start_qt_channel)
        self._raw.connect(self._on_raw)

    def _on_raw(self, data):
        """主通道（工作线程）把字节交回来，在主线程里解析。"""
        if self._done:
            return
        self._handle_bytes(bytes(data))

    # ---------- 发信号（工作线程里也可能调，别让对象已销毁时崩掉） ----------
    def _emit(self, sig, arg):
        try:
            sig.emit(arg)
        except RuntimeError:
            pass

    def _deliver(self, sig, arg):
        """最终结果只发一次：两条通道谁先回来用谁，后到的直接丢掉。"""
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self._hedge.stop()
        self._emit(sig, arg)

    def check(self, current=APP_VERSION, timeout_ms=10000):
        self._current = current or APP_VERSION
        self._timeout_s = max(1, int(timeout_ms / 1000))
        self._done = False
        self._fallback_used = False
        self._extended = False
        self._reply = None
        try:
            ssl_text = ssl.OPENSSL_VERSION
        except Exception:
            ssl_text = "不可用"
        ulog("开始检查更新：本地 %s（Python SSL：%s）" % (self._current, ssl_text))
        pac = _pac_url()
        if pac:
            ulog("系统配置了 PAC：%s（仅记录，本次不走它）" % pac)
        # 主通道用 Python 自带的 SSL：它每次新建连接、只认环境变量里的代理，
        # 不会被 Qt 的连接复用、DNS 缓存或系统代理残留拖住。
        # 同一环境下实测：Qt 空等 12 秒一个字节都没有，这条 3 秒就拿到清单。
        self._start_python_channel()
        self._hedge.start(min(self.HEDGE_MS, max(1000, timeout_ms - 4000)))
        self._timer.start(timeout_ms)

    # ---------- 两条通道 ----------
    def _start_python_channel(self):
        """主通道：Python 自带的 SSL（只开一次）。"""
        if self._done or self._fallback_used:
            return
        self._fallback_used = True
        threading.Thread(target=self._stdlib_fetch, daemon=True).start()

    def _start_qt_channel(self):
        """兜底通道：Qt 的网络栈。主通道迟迟不回时才启动。

        留它是因为打包环境里 Python 的证书链偶尔不完整，而 Qt 自带 OpenSSL
        是随包发出的 —— 两条腿各自可能坏的地方不一样。
        """
        if self._done or self._reply is not None:
            return
        ulog("主通道 %d ms 未返回，同时启动 Qt 通道" % self.HEDGE_MS)
        self._reply = self._nam.get(_request(MANIFEST_URL))
        self._reply.finished.connect(self._on_finished)

    # ---------- 收尾 ----------
    def _on_timeout(self):
        if self._done:
            return
        # 两条腿都还没结果时别立刻判死：再给最后一小段，
        # 比弹一句"超时"然后其实数据马上到了强。
        if not self._extended:
            self._extended = True
            ulog("总时长用完，再等 3 秒收尾")
            self._timer.start(3000)
            return
        ulog("超时：%d 秒没响应" % getattr(self, "_timeout_s", 10))
        reply = self._reply
        if reply is not None:
            try:
                reply.abort()
            except Exception:
                pass
        self._deliver(self.failed, "连接 GitHub 超时，请检查网络或代理后重试。")

    def _on_finished(self):
        if self._done:
            return
        reply = self._reply
        self._reply = None
        try:
            self._finish(reply)
        finally:
            reply.deleteLater()

    def _finish(self, reply):
        err = reply.error()
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0
        if reply.url().toString() != MANIFEST_URL:
            ulog("已跟随重定向：%s" % reply.url().host())

        if status and status != 200:
            ulog("HTTP %s" % status)
            self._deliver(self.failed, _http_hint(int(status)))
            return
        if err:
            # 这条只是兜底：主通道（Python）还在跑，别在这里抢先判死。
            # 两条都失败时由总超时收尾，文案只有一句。
            ulog("Qt 通道失败：%s（等主通道结果）" % reply.errorString())
            return

        self._handle_bytes(bytes(reply.readAll()))

    # ---------- 拿到内容之后：解析 + 验签 + 比版本 ----------
    def _handle_bytes(self, data: bytes):
        if self._done:
            return
        ulog("收到清单 %d 字节" % len(data))
        try:
            doc = json.loads(data.decode("utf-8", "replace"))
        except Exception:
            ulog("清单不是合法 JSON")
            self._deliver(self.failed, "解析更新清单失败（内容不是合法 JSON）。")
            return

        payload, reason = manifest.verify_document(doc)
        if payload is None:
            ulog("验签失败：%s" % reason)
            self._deliver(self.failed, "更新清单校验失败：%s" % reason)
            return

        remote = str(payload.get("version") or "")
        info = parse_manifest(payload, self._current)
        if info is None:
            ulog("远端 %s，不比本地 %s 新：已是最新" % (remote or "?", self._current))
            self._deliver(self.latest, self._current)
            return
        ulog("远端 %s > 本地 %s：发现新版本" % (remote, self._current))
        self._deliver(self.found, info)

    def _stdlib_fetch(self):
        """主通道：两条路同时走，谁先拿到用谁。

        - 直链：一次请求，github.com 能通时最快
        - API ：主站不可达、只有 api / CDN 可达时，只有这条能救回来

        必须并行。顺序试的话第一条要等到超时才轮到第二条，用户等的是两段时间；
        并行时最坏只等最长的那条，最好就是最快的那条。

        这里只做网络，不碰定时器、不碰 QNetworkAccessManager ——
        那些对象属于主线程，跨线程用是崩程序的常见来源。
        """
        t0 = time.time()
        got = []
        lock = threading.Lock()

        def run(fn, label, budget):
            try:
                data = fn(budget)
            except Exception as e:
                ulog("%s失败（%.1fs）：%s: %s"
                     % (label, time.time() - t0, type(e).__name__, e))
                return
            with lock:
                if got:                 # 另一条先成功了，这条的结果直接丢
                    return
                got.append(data)
            ulog("%s拿到清单（%.1fs，%d 字节）"
                 % (label, time.time() - t0, len(data)))
            self._raw.emit(data)

        budget = max(6, self._timeout_s)
        workers = [
            threading.Thread(target=run, daemon=True,
                             args=(fetch_manifest_direct, "直连",
                                   min(5, budget))),
            threading.Thread(target=run, daemon=True,
                             args=(fetch_manifest_via_api, "API ", budget)),
        ]
        for w in workers:
            w.start()
        for w in workers:
            w.join(budget + 3)



class InstallerDownloader(QObject):
    """下载安装包到临时目录，校验大小和 sha256（如果 Release 给了）。"""

    progress = pyqtSignal(int, int)   # 已下载, 总共
    done = pyqtSignal(str)            # 本地路径
    failed = pyqtSignal(str)

    IDLE_TIMEOUT = 25000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = _make_nam(self)
        self._reply = None
        self._file = None
        self._path = ""
        self._expect = 0
        self._digest = ""
        self._done = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    # ---------- 开始 ----------
    def start(self, info: ReleaseInfo, dest_dir: str = ""):
        if not info or not info.asset_url:
            self.failed.emit("该版本未提供可下载的安装包。")
            return
        if not url_allowed(info.asset_url):
            self.failed.emit("安装包地址不在允许的域名下，已拒绝下载：%s" % info.asset_url)
            return
        if not str(info.digest or "").startswith("sha256:"):
            # 没有校验值就没法确认下到的东西是不是原包，宁可不装
            self.failed.emit("更新清单里没有 sha256 校验值，已拒绝下载。")
            return
        dest_dir = dest_dir or update_dir()
        os.makedirs(dest_dir, exist_ok=True)
        self._verified = False
        # 文件名保持纯 ASCII：中文路径交给命令行处理容易出编码问题
        self._path = os.path.join(dest_dir, "wojietu-setup-%s.exe" % (info.version or "new"))
        self._expect = int(info.asset_size or 0)
        self._digest = (info.digest or "").strip().lower()
        self._done = False

        self._file = QFile(self._path)
        if not self._file.open(QIODevice.WriteOnly | QIODevice.Truncate):
            self.failed.emit("无法写入临时目录：%s" % self._path)
            self._file = None
            return

        self._reply = self._nam.get(_request(info.asset_url))
        self._reply.downloadProgress.connect(self._on_progress)
        self._reply.readyRead.connect(self._on_ready_read)
        self._reply.finished.connect(self._on_finished)
        self._timer.start(self.IDLE_TIMEOUT)

    # ---------- 过程 ----------
    def _on_ready_read(self):
        if self._file is None or self._reply is None:
            return
        chunk = self._reply.readAll()
        if not chunk.isEmpty():
            self._file.write(chunk)
            self._timer.start(self.IDLE_TIMEOUT)   # 还有数据就续命

    def _on_progress(self, got, total):
        if total > 0:
            self._expect = total
        self.progress.emit(int(got), int(total) or int(self._expect))

    def _on_timeout(self):
        if self._done:
            return
        self._done = True
        self._abort()
        self.failed.emit("下载超时（%d 秒没有新数据），请检查网络后重试。"
                         % (self.IDLE_TIMEOUT // 1000))

    def _abort(self):
        try:
            if self._reply is not None:
                self._reply.abort()
        except Exception:
            pass
        try:
            if self._file is not None:
                self._file.close()
        except Exception:
            pass
        self._file = None
        self._cleanup_partial()

    def _cleanup_partial(self):
        try:
            if self._path and os.path.exists(self._path) and not self._verified:
                os.remove(self._path)
        except Exception:
            pass

    # ---------- 收尾 ----------
    def _on_finished(self):
        if self._done:
            return
        self._done = True
        self._timer.stop()
        reply = self._reply
        self._on_ready_read()          # 把最后一小段一起写进去
        try:
            self._finish(reply)
        finally:
            reply.deleteLater()

    def _finish(self, reply):
        status = int(reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0)
        err = reply.error()
        if self._file is not None:
            self._file.flush()
            size = self._file.size()
            self._file.close()
            self._file = None
        else:
            size = -1

        if status and status != 200:
            self._verified = False
            self._cleanup_partial()
            self.failed.emit("下载安装包失败：%s" % _http_hint(status))
            return
        if err:
            self._verified = False
            self._cleanup_partial()
            self.failed.emit("下载中断：%s" % reply.errorString())
            return

        actual = os.path.getsize(self._path) if os.path.exists(self._path) else 0
        if actual < 1024 * 64:      # 小于 64KB 肯定不是安装包（多半是错误页）
            self._verified = False
            self._cleanup_partial()
            self.failed.emit("下载到的文件只有 %d 字节，不像是安装包。" % actual)
            return
        if self._expect and abs(actual - self._expect) > 0:
            self._verified = False
            self._cleanup_partial()
            self.failed.emit("下载不完整：应为 %d 字节，实际 %d 字节。" % (self._expect, actual))
            return
        if not _is_pe(self._path):
            self._verified = False
            self._cleanup_partial()
            self.failed.emit("下载到的文件不是 Windows 可执行文件，可能被网络劫持了。")
            return
        if self._digest.startswith("sha256:"):
            want = self._digest.split(":", 1)[1]
            got = sha256_file(self._path)
            if got != want:
                self._verified = False
                self._cleanup_partial()
                self.failed.emit("安装包校验失败（sha256 不一致），已删除，请重试。")
                return
        else:
            # 走到这里说明清单没给校验值（正常流程在 start() 就挡掉了）
            self._verified = False
            self._cleanup_partial()
            self.failed.emit("没有 sha256 校验值，已拒绝安装。")
            return

        self._verified = True
        self.done.emit(self._path)

    _verified = False


def _is_pe(path: str) -> bool:
    """看开头两个字节是不是 MZ —— 挡住「下到一张 HTML 错误页」的情况。"""
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"MZ"
    except Exception:
        return False


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 256), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------- 安装
def build_install_command(installer: str, restart_exe: str = "", restart_args=(),
                          delay_seconds: int = 3, silent: bool = True):
    """拼出交给 cmd 的那一串命令（纯函数，方便测试）。

    先等几秒让本进程彻底退出（否则文件被占用装不上），再安装，
    装完把新版拉起来。silent=False 时保留安装向导界面（万一目录不可写，
    至少用户能看到提示，而不是毫无反应）。
    """
    installer = os.path.abspath(installer)
    restart_exe = os.path.abspath(restart_exe or running_exe())

    steps = []
    if delay_seconds > 0:
        # 用 ping 而不是 timeout：没有控制台的进程里 timeout 会直接报错。
        # 注意步骤之间用 & 连接，ping 万一不可用也不会中断后面的安装。
        steps.append("ping -n %d 127.0.0.1 >nul" % (delay_seconds + 1))
    if silent:
        # /SILENT（不是 /VERYSILENT）：保留安装进度窗口。静默安装是把主程序关掉、
        # 后台换文件，如果连进度窗口都没有，用户在这十几秒里完全看不到反馈。
        # 进度窗口的标题和「正在安装」都来自安装包的语言文件，会显示软件名。
        mode = ("/SILENT /SUPPRESSMSGBOXES /NORESTART /NOCANCEL "
                "/CLOSEAPPLICATIONS")
    else:
        mode = "/NORESTART /NOCANCEL /CLOSEAPPLICATIONS"
    steps.append('start "" /wait "%s" %s "/LOG=%%TEMP%%\\wojietu-update.log"'
                 % (installer, mode))
    argstr = " ".join('"%s"' % a if " " in str(a) else str(a) for a in (restart_args or ()))
    steps.append('start "" "%s"%s' % (restart_exe, (" " + argstr) if argstr else ""))
    return " & ".join(steps)


def build_install_cmdline(installer: str, restart_exe: str = "", restart_args=(),
                          delay_seconds: int = 3, silent: bool = True):
    """交给 CreateProcess 的整行命令：`cmd.exe /c <各步骤>`（纯函数，方便测试）。"""
    exe = comspec()
    exe = '"%s"' % exe if " " in exe else exe
    return "%s /c %s" % (exe, build_install_command(
        installer, restart_exe, restart_args, delay_seconds, silent))


def launch_silent_install(installer: str, restart_exe: str = "", restart_args=(),
                          delay_seconds: int = 3, silent: bool = True):
    """把安装命令丢给一个隐藏的 cmd 执行；本进程应该马上退出。

    这里必须把整行当成 **一个字符串** 交给 Popen。传 list 时 Windows 会按
    MSVC 规则重新拼命令行，把命令里的 " 变成 \"，而 cmd 不认这种转义：
    `start "" /wait "C:\\a\\b.exe"` 会退化成 `start \\`，弹「Windows 找不到
    '\\' 文件」，安装根本不会开始。传字符串则原样进 lpCommandLine，
    由 cmd 自己解析引号。
    """
    cmdline = build_install_cmdline(installer, restart_exe, restart_args,
                                    delay_seconds, silent)
    flags = 0
    if os.name == "nt":
        flags = 0x08000000 | 0x00000200      # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    # 不落地临时 .bat —— 中文路径不会有编码问题
    return subprocess.Popen(cmdline, close_fds=True, creationflags=flags)
