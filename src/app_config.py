# -*- coding: utf-8 -*-
"""配置读写：%APPDATA%\\我爱截图\\config.json"""
import json
import os

APP_NAME = "我爱截图"
APP_ID = "WoAiJieTu"
APP_VERSION = "1.0.0"

DEFAULTS = {
    "config_schema": 2,              # 配置结构版本，用于旧配置迁移
    "hotkey": "Ctrl+Shift+A",         # 截图快捷键（不含 Alt：Alt 组合截不到展开着的菜单）
    "hide_self": True,               # 截图时隐藏自身界面
    "close_action": "tray",          # 点关闭：tray=最小化到托盘 / exit=退出程序
    "pen_color": "#FF3B30",          # 标记颜色
    "text_size": 20,                 # 文字标注字号（像素）
    "text_bold": False,              # 文字标注是否粗体
    "auto_start": False,             # 开机自启
}

CURRENT_SCHEMA = 2


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


class Config:
    """极简配置容器，读写 JSON，带默认值兜底。"""

    def __init__(self):
        self._data = dict(DEFAULTS)
        self.load()

    # ---------- 基础 ----------
    def load(self):
        try:
            # utf-8-sig：别的编辑器/脚本存盘时可能带 BOM，容忍它
            with open(config_path(), "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, dict):
                try:
                    old = int(data.get("config_schema", 1))
                except (TypeError, ValueError):
                    old = 1
                if old < CURRENT_SCHEMA:
                    # v1 的文字标注默认加粗，v2 起改成常规字重
                    data["text_bold"] = False
                    data["config_schema"] = CURRENT_SCHEMA
                for k, v in data.items():
                    if k in DEFAULTS:
                        self._data[k] = v
        except Exception:
            pass

    def save(self):
        try:
            with open(config_path(), "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("保存配置失败:", e)

    # ---------- 访问 ----------
    def get(self, key, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        self._data[key] = value


config = Config()
