# -*- coding: utf-8 -*-
"""一键打包：PyInstaller 生成 dist/我爱截图/，供 Inno Setup 打包成安装程序。"""
import os
import re
import shutil
import subprocess
import sys

import PyQt5

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
ASSETS = os.path.join(ROOT, "assets")
WORK = os.path.join(ROOT, "build", "pyi")
DIST = os.path.join(ROOT, "dist")
APP_NAME = "我爱截图"
QT_BIN = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "bin")

# Qt 5.15 建立 HTTPS 连接时会动态加载 OpenSSL 的两个库。
# PyInstaller 只会带上 libcrypto，漏掉 libssl —— 结果装好的软件一检查更新就报
# "TLS initialization failed"，源码里跑却完全正常（PyQt5 的 bin 目录里两个都有）。
# 而且这两个库只认 exe 同级目录，放进 _internal 一样找不到，所以打包后手动复制。
OPENSSL_DLLS = (
    "libssl-1_1-x64.dll",
    "libcrypto-1_1-x64.dll",
)


def _app_version() -> str:
    """默认版本号直接读源码，免得打包脚本里的数字和 app_config 对不上。"""
    try:
        with open(os.path.join(SRC, "app_config.py"), encoding="utf-8-sig") as f:
            m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', f.read())
            return m.group(1) if m else "0.0.0"
    except OSError:
        return "0.0.0"


# 版本号可用环境变量 APP_VERSION 覆盖（CI 里按 tag 传入），默认跟源码一致
VERSION = (os.environ.get("APP_VERSION") or _app_version()).strip()


def _version_parts(text):
    """把 1.2.3 / v1.2.3 这类型号拆成三个整数，缺的补 0。"""
    parts = []
    for piece in text.replace("-", ".").replace("_", ".").split("."):
        if piece.isdigit():
            parts.append(int(piece))
            if len(parts) == 3:
                break
    while len(parts) < 3:
        parts.append(0)
    return parts


_V1, _V2, _V3 = _version_parts(VERSION)
V4 = "%d.%d.%d.0" % (_V1, _V2, _V3)

VERSION_FILE = r"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(%(a)d, %(b)d, %(c)d, 0),
    prodvers=(%(a)d, %(b)d, %(c)d, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404B0',
        [StringStruct('CompanyName', 'WoAiJieTu'),
         StringStruct('FileDescription', '我爱截图 - Windows 截图工具'),
         StringStruct('FileVersion', '%(v4)s'),
         StringStruct('InternalName', 'WoAiJieTu'),
         StringStruct('OriginalFilename', 'WoAiJieTu.exe'),
         StringStruct('ProductName', '我爱截图'),
         StringStruct('ProductVersion', '%(v4)s')])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
""" % {"a": _V1, "b": _V2, "c": _V3, "v4": V4}


def main():
    print("版本:", VERSION)
    os.makedirs(WORK, exist_ok=True)
    vfile = os.path.join(WORK, "version_info.txt")
    with open(vfile, "w", encoding="utf-8") as f:
        f.write(VERSION_FILE)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed",
        "--name", APP_NAME,
        "--icon", os.path.join(ASSETS, "app.ico"),
        "--add-data", ASSETS + os.pathsep + "assets",
        "--version-file", vfile,
        "--distpath", DIST,
        "--workpath", WORK,
        "--specpath", WORK,
        "--log-level", "WARN",
    ]
    cmd.append(os.path.join(SRC, "main.py"))
    print("running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("PyInstaller 失败，退出码", result.returncode)
        return result.returncode

    # Qt 的 OpenSSL 是运行时用 LoadLibrary 现找的，只认 exe 所在目录 ——
    # 放进 _internal 它会视而不见。缺了这两个库，装好的软件一检查更新就报
    # "TLS initialization failed"。约 4.5 MB。
    for name in OPENSSL_DLLS:
        src_dll = os.path.join(QT_BIN, name)
        if os.path.exists(src_dll):
            shutil.copy2(src_dll, os.path.join(DIST, APP_NAME, name))

    exe = os.path.join(DIST, APP_NAME, APP_NAME + ".exe")
    if not os.path.exists(exe):
        print("未找到生成的 exe:", exe)
        return 1

    # 少了 libssl 的包装上去也「能启动」，只是检查更新永远报 TLS 初始化失败，
    # 所以在这里直接卡住，别让它流到 Release 里。
    bundle = os.path.join(DIST, APP_NAME)
    missing = [n for n in OPENSSL_DLLS
               if not os.path.exists(os.path.join(bundle, n))]
    if missing:
        print("打包产物缺少 %s，装好后检查更新会报 TLS 失败。" % ", ".join(missing))
        return 1

    size = os.path.getsize(exe) / 1024 / 1024
    total = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fs in os.walk(os.path.join(DIST, APP_NAME)) for f in fs
    ) / 1024 / 1024
    print("\n打包完成：", exe)
    print("主程序 %.1f MB，目录合计 %.1f MB" % (size, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
