# -*- coding: utf-8 -*-
"""一键打包：PyInstaller 生成 dist/我爱截图/，供 Inno Setup 打包成安装程序。"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
ASSETS = os.path.join(ROOT, "assets")
WORK = os.path.join(ROOT, "build", "pyi")
DIST = os.path.join(ROOT, "dist")
APP_NAME = "我爱截图"
# 版本号可用环境变量 APP_VERSION 覆盖（CI 里按 tag 传入），默认 1.0.1
VERSION = (os.environ.get("APP_VERSION") or "1.0.1").strip()


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
        os.path.join(SRC, "main.py"),
    ]
    print("running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("PyInstaller 失败，退出码", result.returncode)
        return result.returncode

    exe = os.path.join(DIST, APP_NAME, APP_NAME + ".exe")
    if not os.path.exists(exe):
        print("未找到生成的 exe:", exe)
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
