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
import os
import re
import subprocess
import sys
import tempfile

from PyQt5.QtCore import QFile, QIODevice, QObject, QTimer, QUrl, pyqtSignal
from PyQt5.QtNetwork import (
    QNetworkAccessManager, QNetworkProxyFactory, QNetworkRequest,
)

from app_config import APP_NAME, APP_VERSION
import manifest

# ---------------------------------------------------------------- 常量
# 只改这一行就能换仓库
REPO = "zhuwm001/WinScreenshot-Utility"
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


# ---------------------------------------------------------------- 网络
def _token() -> str:
    return (os.environ.get("WOJIETU_GITHUB_TOKEN") or "").strip()


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
        return ("没找到更新清单（HTTP 404）。可能是还没发布带 latest.json 的版本，"
                "或者仓库又改回 Private 了。")
    if status in (403, 429):
        return "GitHub 拒绝访问（HTTP %d），可能是访问太频繁，过一会儿再试。" % status
    if status >= 500:
        return "GitHub 服务器暂时出问题（HTTP %d），过一会儿再试。" % status
    return "GitHub 返回 HTTP %d。" % status


def _network_error(detail: str) -> str:
    """把 Qt 的英文错误翻成人话；TLS 那条最容易让人以为是网络断了。"""
    detail = detail or "未知错误"
    low = detail.lower()
    if "tls initialization" in low or "ssl handshake" in low:
        return ("无法建立加密连接（%s）。请确认系统时间正确、网络能访问 GitHub；"
                "如果用了代理，确认代理支持 HTTPS。" % detail)
    if "host not found" in low or "unknown error" in low:
        return "解析不到 GitHub 域名（DNS 失败），请检查网络或代理设置。"
    if "connection refused" in low or "connection closed" in low:
        return "连接被中断（%s），可能是代理或防火墙拦截。" % detail
    return "网络连接失败：%s" % detail


class UpdateChecker(QObject):
    """异步检查一次最新版本。三种结果三选一，不会都发。

    只认**签过名**的清单（latest.json）：拿不到或验签不过一律失败，
    绝不退回去用未签名的数据。
    """

    found = pyqtSignal(object)     # ReleaseInfo
    latest = pyqtSignal(str)       # 当前版本，已是最新
    failed = pyqtSignal(str)       # 人话版错误

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = _make_nam(self)
        self._reply = None
        self._done = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def check(self, current=APP_VERSION, timeout_ms=12000):
        self._current = current or APP_VERSION
        self._done = False
        self._reply = self._nam.get(_request(MANIFEST_URL))
        self._reply.finished.connect(self._on_finished)
        self._timer.start(timeout_ms)

    # ---------- 收尾 ----------
    def _on_timeout(self):
        if self._done:
            return
        self._done = True
        try:
            self._reply.abort()
        except Exception:
            pass
        self.failed.emit("连接 GitHub 超时，请检查网络或代理后重试。")

    def _on_finished(self):
        if self._done:
            return
        self._done = True
        self._timer.stop()
        reply = self._reply
        try:
            self._finish(reply)
        finally:
            reply.deleteLater()

    def _finish(self, reply):
        err = reply.error()
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0

        if status and status != 200:
            self.failed.emit(_http_hint(int(status)))
            return
        if err:
            self.failed.emit(_network_error(reply.errorString()))
            return

        try:
            import json
            doc = json.loads(bytes(reply.readAll()).decode("utf-8", "replace"))
        except Exception:
            self.failed.emit("解析更新清单失败（内容不是合法 JSON）。")
            return

        payload, reason = manifest.verify_document(doc)
        if payload is None:
            self.failed.emit("更新清单校验失败：%s" % reason)
            return

        info = parse_manifest(payload, self._current)
        if info is None:
            self.latest.emit(self._current)
            return
        self.found.emit(info)


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
            self.failed.emit("这个版本没有可下载的安装包。")
            return
        if not url_allowed(info.asset_url):
            self.failed.emit("安装包地址不在允许的域名下，已拒绝下载：%s" % info.asset_url)
            return
        if not str(info.digest or "").startswith("sha256:"):
            # 没有校验值就没法确认下到的东西是不是原包，宁可不装
            self.failed.emit("更新清单里没有 sha256 校验值，已拒绝下载。")
            return
        dest_dir = dest_dir or tempfile.gettempdir()
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
                          delay_seconds: int = 3):
    """拼出交给 cmd 的那一串命令（纯函数，方便测试）。

    先等几秒让本进程彻底退出（否则文件被占用装不上），
    再 /VERYSILENT 静默安装，装完把新版拉起来。
    """
    installer = os.path.abspath(installer)
    restart_exe = os.path.abspath(restart_exe or running_exe())

    steps = []
    if delay_seconds > 0:
        # 用 ping 而不是 timeout：没有控制台的进程里 timeout 会直接报错
        steps.append("ping -n %d 127.0.0.1 >nul" % (delay_seconds + 1))
    steps.append(
        'start "" /wait "%s" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOCANCEL '
        '/CLOSEAPPLICATIONS /LOG="%%TEMP%%\\wojietu-update.log"' % installer)
    args = " ".join('"%s"' % a if " " in str(a) else str(a) for a in (restart_args or ()))
    steps.append('start "" "%s"%s' % (restart_exe, (" " + args) if args else ""))
    return " & ".join(steps)


def launch_silent_install(installer: str, restart_exe: str = "", restart_args=(),
                          delay_seconds: int = 3):
    """把安装命令丢给一个隐藏的 cmd 执行；本进程应该马上退出。"""
    command = build_install_command(installer, restart_exe, restart_args, delay_seconds)
    comspec = os.environ.get("COMSPEC") or "cmd.exe"
    flags = 0
    if os.name == "nt":
        flags = 0x08000000 | 0x00000200      # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    # 整串命令作为 Unicode 参数传进去，不落地临时 .bat —— 中文路径不会有编码问题
    proc = subprocess.Popen([comspec, "/c", command], close_fds=True,
                            creationflags=flags)
    return proc
