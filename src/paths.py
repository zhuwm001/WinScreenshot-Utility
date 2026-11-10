# -*- coding: utf-8 -*-
"""资源路径工具（兼容 PyInstaller 打包后运行）。"""
import os
import sys


def app_root() -> str:
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts) -> str:
    return os.path.join(app_root(), *parts)


def asset(name: str) -> str:
    return resource_path("assets", name)
