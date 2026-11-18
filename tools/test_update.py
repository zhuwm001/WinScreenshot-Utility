# -*- coding: utf-8 -*-
"""更新模块自检（不联网也能跑；加 --live 才会真的问 GitHub）。

    python tools/test_update.py
    python tools/test_update.py --live
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

import qt_env  # noqa: E402  Qt 平台插件路径统一处理，避免弹 no Qt platform plugin
qt_env.setup()

import update as up  # noqa: E402

PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  [ok]   %s%s" % (name, ("  " + detail) if detail else ""))
    else:
        FAIL += 1
        print("  [FAIL] %s%s" % (name, ("  " + detail) if detail else ""))


FAKE_RELEASE = {
    "tag_name": "v1.1.0",
    "name": "我爱截图 v1.1.0",
    "body": "### 更新内容\n\n- 修复副屏黑块 [#12](https://x/12) (a1b2c3d)\n**重点** 优化",
    "html_url": "https://github.com/zhuwm001/WinScreenshot-Utility/releases/tag/v1.1.0",
    "published_at": "2026-11-15T13:20:00Z",
    "assets": [
        {"name": "checksums.zip", "size": 1234,
         "browser_download_url": "https://x/checksums.zip"},
        {"name": "我爱截图_安装包_v1.1.0.exe", "size": 29000000,
         "browser_download_url": "https://x/setup.exe",
         "digest": "sha256:abc"},
        {"name": "SHA256SUMS.txt", "size": 100, "browser_download_url": "https://x/sums"},
    ],
}


def test_version():
    print("\n== 版本号解析 / 比较 ==")
    check("v1.0.2", up.parse_version("v1.0.2") == (1, 0, 2))
    check("1.2 补零", up.parse_version("1.2") == (1, 2, 0))
    check("带后缀", up.parse_version("1.0.2-beta1") == (1, 0, 2))
    check("垃圾输入", up.parse_version("") == () and up.parse_version("abc") == ())
    check("新版更新", up.is_newer("1.1.0", "1.0.1"))
    check("同版不更新", not up.is_newer("1.0.1", "1.0.1"))
    check("旧版不更新", not up.is_newer("0.9.9", "1.0.1"))
    check("多位数比较", up.is_newer("1.10.0", "1.9.9"))
    check("解析失败当不更新", not up.is_newer("abc", "1.0.1"))


def test_notes():
    print("\n== 更新说明排版 ==")
    text = up.plain_notes(FAKE_RELEASE["body"])
    check("去掉井号", "###" not in text)
    check("列表换成圆点", "· " in text)
    check("去掉加粗星号", "**" not in text)
    check("去掉 commit 链接", "a1b2c3d" not in text, repr(text[:40]))
    long_text = up.plain_notes("- x\n" * 3000)
    check("超长截断", len(long_text) <= 4010, "len=%d" % len(long_text))


def test_parse():
    print("\n== Release 解析 ==")
    info = up.parse_release(FAKE_RELEASE, "1.0.1")
    check("识别到新版本", info is not None)
    if info:
        check("版本号", info.version == "1.1.0", info.version)
        check("挑中安装包", info.asset_name.endswith(".exe"), info.asset_name)
        check("拿到下载地址", info.asset_url == "https://x/setup.exe")
        check("大小文本", info.size_text == "27.7 MB", info.size_text)
        check("sha256 摘要", info.digest == "sha256:abc")
    check("同版本返回 None", up.parse_release(FAKE_RELEASE, "1.1.0") is None)
    check("allow_same 可取到", up.parse_release(FAKE_RELEASE, "1.1.0", allow_same=True) is not None)

    no_exe = dict(FAKE_RELEASE, assets=[{"name": "a.zip", "size": 1,
                                         "browser_download_url": "https://x/a.zip"}])
    info2 = up.parse_release(no_exe, "1.0.1")
    check("没有 exe 也能解析", info2 is not None and not info2.has_installer)

    check("pick 忽略非 exe", up.pick_installer_asset([{"name": "x.zip"}]) is None)
    check("pick 空列表", up.pick_installer_asset(None) is None)


def test_command():
    print("\n== 静默安装命令 ==")
    cmd = up.build_install_command(
        r"C:\Temp\wojietu-setup-1.1.0.exe",
        r"C:\Users\a b\AppData\Local\Programs\我爱截图\我爱截图.exe",
        ["--autostart"], delay_seconds=3)
    check("等待退出", "ping -n 4 127.0.0.1" in cmd)
    check("静默参数", "/VERYSILENT" in cmd and "/SUPPRESSMSGBOXES" in cmd)
    check("不自动重启系统", "/NORESTART" in cmd)
    check("允许关闭占用程序", "/CLOSEAPPLICATIONS" in cmd)
    check("路径带引号", '"C:\\Temp\\wojietu-setup-1.1.0.exe"' in cmd)
    check("重启参数保留", "--autostart" in cmd)
    check("日志落在 TEMP", "%TEMP%\\wojietu-update.log" in cmd)
    check("安装完再拉起", cmd.rstrip().endswith("--autostart"))
    no_wait = up.build_install_command("C:\\a.exe", "C:\\b.exe", [], delay_seconds=0)
    check("可关闭等待", "ping" not in no_wait)


def test_launch_cmdline():
    """回归：交给 cmd 的那一行不能被 Windows 重新转义。

    以前是 Popen([comspec, "/c", command])，Windows 会按 MSVC 规则把命令里的
    " 变成 \"，cmd 不认这种转义，`start "" /wait "x.exe"` 退化成 `start \`，
    弹「Windows 找不到 '\\' 文件」，安装完全没开始。
    """
    print("\n== 交给 cmd 的命令行 ==")
    installer = r"C:\Users\a b\AppData\Local\Temp\wojietu-setup-1.1.4.exe"
    restart = r"E:\我爱截图\我爱截图.exe"

    line = up.build_install_cmdline(installer, restart, ["--autostart"], 3)
    check("以 cmd /c 开头", " /c ping -n 4 " in line, line[:46] + "…")
    check("没有 \\\" 这种转义", '\\"' not in line)
    check("安装包路径原样带引号", '"%s"' % installer in line)
    check("重启路径原样带引号", '"%s"' % restart in line)

    # 旧写法确实会被转义：证明这条回归测试抓的是真问题
    legacy = subprocess.list2cmdline(
        [os.environ.get("COMSPEC") or "cmd.exe", "/c",
         up.build_install_command(installer, restart, [], 3)])
    check("旧写法会被转义（回归证据）", '\\"' in legacy)

    # Popen 必须收到字符串，而不是 list
    seen = []
    real_popen = up.subprocess.Popen

    class _Fake:
        pass

    def _fake(args, **kw):
        seen.append((args, kw))
        return _Fake()

    up.subprocess.Popen = _fake
    try:
        up.launch_silent_install(installer, restart, [], delay_seconds=0)
    finally:
        up.subprocess.Popen = real_popen
    check("Popen 收到整行字符串", seen and isinstance(seen[0][0], str),
          type(seen[0][0]).__name__ if seen else "未调用")
    check("隐藏窗口启动", bool(seen and seen[0][1].get("creationflags", 0) & 0x08000000))


def test_install_helpers():
    """安装回执、安装包目录、静默/非静默两套参数。"""
    print("\n== 安装回执与路径 ==")
    d = tempfile.mkdtemp(prefix="wojietu-test-")
    real = up.update_dir
    up.update_dir = lambda: d
    try:
        check("写回执", bool(up.write_pending("1.2.0", r"C:\a\wojietu-setup-1.2.0.exe")))
        got = up.read_pending()
        check("读回执", got.get("version") == "1.2.0", str(got))
        up.clear_pending()
        check("清回执", up.read_pending() == {})

        for n in ("wojietu-setup-1.1.0.exe", "wojietu-setup-1.1.1.exe", "note.txt"):
            with open(os.path.join(d, n), "wb") as f:
                f.write(b"x")
        up.cleanup_installers(keep="wojietu-setup-1.1.1.exe")
        left = sorted(os.listdir(d))
        check("只留正在用的安装包", left == ["note.txt", "wojietu-setup-1.1.1.exe"], str(left))
    finally:
        up.update_dir = real
        shutil.rmtree(d, ignore_errors=True)

    check("从文件名取版本", up.version_from_installer(r"C:\x\wojietu-setup-1.1.6.exe") == "1.1.6")
    check("别的文件名取不到版本", up.version_from_installer(r"C:\x\a.exe") == "")
    check("cmd 路径真实存在", os.path.isfile(up.comspec()), up.comspec())
    check("安装目录可写", up.install_dir_writable())

    ui = up.build_install_command(r"C:\a\b.exe", r"C:\c\d.exe", [], 0, silent=False)
    check("非静默不带 /VERYSILENT", "/VERYSILENT" not in ui and "/SUPPRESSMSGBOXES" not in ui)
    check("非静默仍会拉起新版", ui.rstrip().endswith('"C:\\c\\d.exe"'), ui[-24:])


def test_local():
    print("\n== 本机环境 ==")
    print("     运行中的 exe : %s" % up.running_exe())
    check("running_exe 返回绝对路径", os.path.isabs(up.running_exe()))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(b"MZ" + b"x" * 1000)
        path = f.name
    try:
        check("sha256 计算", len(up.sha256_file(path)) == 64)
        check("PE 头识别", up._is_pe(path))
        notpe = path + ".txt"
        with open(notpe, "wb") as f2:
            f2.write(b"<html>")
        check("非 PE 识别", not up._is_pe(notpe))
        os.remove(notpe)
    finally:
        os.remove(path)


def test_live():
    print("\n== 真连 GitHub ==")
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    result = {}

    checker = up.UpdateChecker()
    checker.found.connect(lambda i: (result.update(kind="found", info=i), app.quit()))
    checker.latest.connect(lambda v: (result.update(kind="latest", ver=v), app.quit()))
    checker.failed.connect(lambda m: (result.update(kind="failed", msg=m), app.quit()))
    checker.check("1.0.0", timeout_ms=20000)
    QTimer.singleShot(25000, app.quit)
    app.exec_()

    kind = result.get("kind")
    if kind == "found":
        i = result["info"]
        print("     远端最新：%s  安装包：%s  %s" % (i.version, i.asset_name, i.size_text))
        check("能读到 Release", True, i.version)
    elif kind == "latest":
        check("能读到 Release", True, "当前已是最新 %s" % result.get("ver"))
    else:
        check("能读到 Release", False, result.get("msg") or "无响应")


def main():
    print("更新模块自检  当前版本 %s" % up.APP_VERSION)
    test_version()
    test_notes()
    test_parse()
    test_command()
    test_launch_cmdline()
    test_install_helpers()
    test_local()
    if "--live" in sys.argv:
        test_live()
    print("\n通过 %d / 失败 %d" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
