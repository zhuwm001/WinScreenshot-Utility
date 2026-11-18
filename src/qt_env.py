# -*- coding: utf-8 -*-
r"""统一 Qt 平台插件路径。

背景：本机用源码方式跑（`python src/main.py` 或 `python tools/xxx.py`）时，
Qt 偶尔找不到可加载的平台插件，弹窗「This application failed to start because
no Qt platform plugin could be initialized」，进程直接退出——窗口、遮罩、截图
全都不会出现，而且每起一个进程就弹一个，看着像"不停弹"。

原因是进程启动时 Qt 的插件搜索路径没有落在 PyQt5 自带的 plugins 目录上
（换过盘的 Python、受限终端启动、PATH 里混进别的 Qt 运行时都会触发）。
这里在建 QApplication 之前把它们显式指过去，源码运行不再依赖外部环境变量。

打包产物不受影响：PyInstaller 环境下直接跳过，继续用 _internal 里自己的布局。
"""
from __future__ import annotations

import os
import sys

_DLL_DIRS = []  # 必须持有句柄，否则 add_dll_directory 会被回收


def setup(verbose: bool = False) -> str:
    """把 Qt 插件目录指到 PyQt5 自带的位置。返回实际使用的插件目录，失败返回空串。"""
    if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
        return ""  # 打包后由 PyInstaller 负责，别插手

    try:
        import importlib.util

        spec = importlib.util.find_spec("PyQt5")
        origin = getattr(spec, "origin", None) if spec else None
        if not origin:
            return ""
        base = os.path.dirname(os.path.abspath(origin))
    except Exception:
        return ""

    plugins = os.path.join(base, "Qt5", "plugins")
    platforms = os.path.join(plugins, "platforms")
    bin_dir = os.path.join(base, "Qt5", "bin")

    # 插件 DLL 本身在不在，先判掉再改环境，避免把错路径写死
    if not os.path.isfile(os.path.join(platforms, "qwindows.dll")):
        return ""

    # 已经指向有效目录就不覆盖（CI / 用户显式设置优先）
    cur = os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH")
    if not (cur and os.path.isfile(os.path.join(cur, "qwindows.dll"))):
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms
    cur = os.environ.get("QT_PLUGIN_PATH")
    if not (cur and os.path.isdir(cur)):
        os.environ["QT_PLUGIN_PATH"] = plugins

    # Qt5Core.dll 等运行时库所在目录，让 Windows 能就近解析依赖
    if os.path.isdir(bin_dir):
        try:
            _DLL_DIRS.append(os.add_dll_directory(bin_dir))
        except (AttributeError, OSError):
            pass

    if verbose:
        print("Qt plugins:", plugins)
        print("QT_QPA_PLATFORM_PLUGIN_PATH:", os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"))
        print("QT_PLUGIN_PATH:", os.environ.get("QT_PLUGIN_PATH"))
    return plugins


if __name__ == "__main__":
    print("found:", setup(verbose=True) or "(未找到 PyQt5 插件目录)")
