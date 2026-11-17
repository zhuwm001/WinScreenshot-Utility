# -*- coding: utf-8 -*-
"""全局视觉常量。"""

PRIMARY = "#4A86FF"
PRIMARY_DARK = "#3A6FE0"
ACCENT = "#8B5CF6"

BG = "#FFFFFF"
BG_SOFT = "#F5F7FB"
TEXT = "#1F2330"
TEXT_SUB = "#6B7280"
BORDER = "#E6EAF2"

DANGER = "#FF3B30"
WARN = "#E07B00"

FONT_FAMILY = '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif'

# 标记调色板
PALETTE = [
    "#FF3B30",  # 红
    "#FF9500",  # 橙
    "#FFCC00",  # 黄
    "#34C759",  # 绿
    "#4A86FF",  # 蓝
    "#8B5CF6",  # 紫
    "#FFFFFF",  # 白
    "#1F2330",  # 黑
]


def main_window_qss():
    return f"""
    QWidget {{
        font-family: {FONT_FAMILY};
        color: {TEXT};
    }}
    QLabel#title {{
        font-size: 22px;
        font-weight: 600;
        color: {TEXT};
    }}
    QLabel#subtitle {{
        font-size: 12px;
        color: #8A93A6;
    }}
    QLabel#author {{
        font-size: 11px;
        color: #A8B0C0;
    }}
    QLabel#hotkeyBadge {{
        font-size: 12px;
        color: {TEXT_SUB};
        background: {BG_SOFT};
        border: 1px solid {BORDER};
        border-radius: 9px;
        padding: 2px 9px;
    }}
    QPushButton#capture {{
        font-size: 16px;
        font-weight: 600;
        color: #FFFFFF;
        border: none;
        border-radius: 12px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                    stop:0 {PRIMARY}, stop:1 {ACCENT});
    }}
    QPushButton#capture:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                    stop:0 #5C93FF, stop:1 #9A70F8);
    }}
    QPushButton#capture:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                    stop:0 {PRIMARY_DARK}, stop:1 #7C4EE0);
    }}
    QPushButton#ghost {{
        font-size: 13px;
        color: {TEXT_SUB};
        border: 1px solid {BORDER};
        border-radius: 9px;
        background: #FFFFFF;
        padding: 7px 14px;
    }}
    QPushButton#ghost:hover {{
        color: {PRIMARY};
        border-color: {PRIMARY};
        background: #F2F6FF;
    }}
    QPushButton#ghost:pressed {{
        background: #E8F0FF;
    }}
    QToolButton#winbtn {{
        border: none;
        border-radius: 6px;
        background: transparent;
    }}
    QToolButton#winbtn:hover {{
        background: #EEF1F7;
    }}
    """


def dialog_qss():
    return f"""
    QDialog {{
        background: {BG};
        font-family: {FONT_FAMILY};
        color: {TEXT};
    }}
    QLabel {{
        color: {TEXT};
        font-size: 13px;
    }}
    QLabel#sectionTitle {{
        font-size: 12px;
        font-weight: 600;
        color: {TEXT_SUB};
    }}
    QLabel#hint {{
        font-size: 12px;
        color: #7C8598;
    }}
    QLabel#versionText {{
        font-size: 14px;
        font-weight: 600;
        color: {TEXT};
    }}
    QFrame#card {{
        background: {BG_SOFT};
        border: 1px solid #EAEEF6;
        border-radius: 10px;
    }}
    QRadioButton, QCheckBox {{
        font-size: 13px;
        color: {TEXT};
        spacing: 8px;
        padding: 3px 0;
    }}
    QPushButton {{
        font-size: 13px;
        border-radius: 8px;
        padding: 7px 20px;
        border: 1px solid {BORDER};
        background: #FFFFFF;
        color: {TEXT};
    }}
    QPushButton:hover {{
        border-color: {PRIMARY};
        color: {PRIMARY};
    }}
    QPushButton#primary {{
        background: {PRIMARY};
        border: 1px solid {PRIMARY};
        color: #FFFFFF;
        font-weight: 600;
    }}
    QPushButton#primary:hover {{
        background: {PRIMARY_DARK};
        border-color: {PRIMARY_DARK};
        color: #FFFFFF;
    }}
    QLineEdit#hotkey {{
        font-size: 14px;
        font-weight: 600;
        color: {TEXT};
        background: #FFFFFF;
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 8px 12px;
    }}
    QToolButton#updateBtn {{
        border: none;
        border-radius: 6px;
        background: transparent;
    }}
    QToolButton#updateBtn:hover {{
        background: #E9F9EF;
    }}
    QLineEdit#hotkey[recording="true"] {{
        border: 1px solid {PRIMARY};
        background: #F2F6FF;
        color: {PRIMARY};
    }}
    QLineEdit#hotkey[invalid="true"] {{
        border: 1px solid {DANGER};
        background: #FFF2F1;
        color: {DANGER};
    }}
    """
