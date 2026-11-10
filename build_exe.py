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
VERSION = "1.0.0"

VERSION_FILE = r"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
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
         StringStruct('FileVersion', '1.0.0.0'),
         StringStruct('InternalName', 'WoAiJieTu'),
         StringStruct('OriginalFilename', 'WoAiJieTu.exe'),
         StringStruct('ProductName', '我爱截图'),
         StringStruct('ProductVersion', '1.0.0.0')])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def main():
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
