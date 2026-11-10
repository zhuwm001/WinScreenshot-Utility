# -*- coding: utf-8 -*-
"""设置对话框：截图行为、关闭行为、开机启动、全局快捷键。"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QRadioButton, QVBoxLayout,
)

import theme
from app_config import APP_NAME, DEFAULTS
import autostart
from hotkey import contains_alt

# Qt 键 -> 配置里使用的键名
_QT_SPECIAL = {
    Qt.Key_Print: "PrintScreen",
    Qt.Key_Insert: "Insert",
    Qt.Key_Delete: "Delete",
    Qt.Key_Home: "Home",
    Qt.Key_End: "End",
    Qt.Key_PageUp: "PageUp",
    Qt.Key_PageDown: "PageDown",
    Qt.Key_Space: "Space",
    Qt.Key_Tab: "Tab",
    Qt.Key_Left: "Left",
    Qt.Key_Right: "Right",
    Qt.Key_Up: "Up",
    Qt.Key_Down: "Down",
    Qt.Key_QuoteLeft: "`",
    Qt.Key_Minus: "-",
    Qt.Key_Equal: "=",
    Qt.Key_BracketLeft: "[",
    Qt.Key_BracketRight: "]",
    Qt.Key_Backslash: "\\",
    Qt.Key_Semicolon: ";",
    Qt.Key_Apostrophe: "'",
    Qt.Key_Comma: ",",
    Qt.Key_Period: ".",
    Qt.Key_Slash: "/",
}

_MODIFIER_KEYS = {
    Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
    Qt.Key_AltGr, Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock,
}


def qt_key_to_name(key: int) -> str:
    if Qt.Key_A <= key <= Qt.Key_Z:
        return chr(key)
    if Qt.Key_0 <= key <= Qt.Key_9:
        return chr(key)
    if Qt.Key_F1 <= key <= Qt.Key_F24:
        return "F%d" % (key - Qt.Key_F1 + 1)
    return _QT_SPECIAL.get(key, "")


def mods_to_text(mods) -> str:
    parts = []
    if mods & Qt.ControlModifier:
        parts.append("Ctrl")
    if mods & Qt.AltModifier:
        parts.append("Alt")
    if mods & Qt.ShiftModifier:
        parts.append("Shift")
    if mods & Qt.MetaModifier:
        parts.append("Win")
    return "+".join(parts)


def repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class HotkeyEdit(QLineEdit):
    """点击后直接按键录制的输入框。"""

    valueChanged = pyqtSignal(str)

    def __init__(self, value: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("hotkey")
        self.setReadOnly(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(38)
        self._value = value
        self._recording = False
        self._preview = ""
        self.setText(value or "点击此处后按下组合键")

    # ---------- 录制 ----------
    def begin_recording(self):
        self._recording = True
        self._preview = ""
        self.setProperty("recording", "true")
        repolish(self)
        self.setText("请按下新的组合键…")

    def stop_recording(self):
        self._recording = False
        self._preview = ""
        self.setProperty("recording", "false")
        repolish(self)
        self.setText(self._value or "点击此处后按下组合键")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self.begin_recording()
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        if self._recording:
            self.stop_recording()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if not self._recording:
            self.begin_recording()
            return

        key = event.key()
        mods = event.modifiers()

        if key in _MODIFIER_KEYS:
            text = mods_to_text(mods)
            self.setText((text + " + …") if text else "请按下新的组合键…")
            return

        if key == Qt.Key_Escape:
            self.stop_recording()
            self.clearFocus()
            return

        # 先确定主键名
        name = qt_key_to_name(key)
        if key == Qt.Key_Backspace or key == Qt.Key_Delete:
            self._value = ""
            self.valueChanged.emit("")
            self.stop_recording()
            return

        if not name:
            self.setText("该按键不支持，请换一个")
            return

        if mods == Qt.NoModifier:
            self.setText("需要配合 Ctrl / Alt / Shift / Win")
            return

        self._value = "%s+%s" % (mods_to_text(mods), name)
        self._recording = False
        self.setProperty("recording", "false")
        repolish(self)
        self.setText(self._value)
        self.valueChanged.emit(self._value)

    # ---------- 取值 ----------
    def value(self) -> str:
        return self._value

    def set_value(self, value: str):
        self._value = value or ""
        if not self._recording:
            self.setText(self._value or "点击此处后按下组合键")
        self.valueChanged.emit(self._value)


class SettingsDialog(QDialog):
    def __init__(self, cfg, try_apply_hotkey, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._try_apply_hotkey = try_apply_hotkey

        self.setWindowTitle("设置 - %s" % APP_NAME)
        self.setWindowIcon(QIcon("assets/app.ico"))
        self.setStyleSheet(theme.dialog_qss())
        self.setMinimumWidth(500)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(12)

        # ---------------- 截图行为 ----------------
        body = self._card("截图", root)
        self.chk_hide = QCheckBox("截图时隐藏「%s」窗口" % APP_NAME)
        self.chk_hide.setChecked(bool(cfg.get("hide_self")))
        body.addWidget(self.chk_hide)
        body.addWidget(self._hint("截图瞬间自动隐藏本软件窗口，截图里不会出现软件界面。"))

        # ---------------- 关闭按钮 ----------------
        body = self._card("点击窗口关闭按钮时", root)
        self.rb_tray = QRadioButton("隐藏到托盘")
        self.rb_exit = QRadioButton("直接退出程序")
        if cfg.get("close_action") == "exit":
            self.rb_exit.setChecked(True)
        else:
            self.rb_tray.setChecked(True)
        body.addWidget(self.rb_tray)
        body.addWidget(self.rb_exit)
        body.addWidget(self._hint("隐藏到托盘：点「×」后程序继续在桌面右下角托盘区运行，双击图标可再打开。"))

        # ---------------- 开机启动 ----------------
        body = self._card("开机启动", root)
        self.chk_auto = QCheckBox("开机时自动启动「%s」" % APP_NAME)
        self.chk_auto.setChecked(bool(cfg.get("auto_start")))
        body.addWidget(self.chk_auto)
        body.addWidget(self._hint("登录 Windows 后自动在桌面右下角托盘区运行，不弹出主界面，"
                                 "按快捷键即可截图。"))
        self.lbl_auto_error = QLabel("")
        self.lbl_auto_error.setStyleSheet("color: %s; font-size: 12px;" % theme.DANGER)
        self.lbl_auto_error.setWordWrap(True)
        self.lbl_auto_error.hide()
        body.addWidget(self.lbl_auto_error)

        # ---------------- 快捷键 ----------------
        body = self._card("截图快捷键", root)
        self.hotkey_edit = HotkeyEdit(cfg.get("hotkey", ""))
        self.hotkey_edit.valueChanged.connect(self._on_hotkey_changed)
        body.addWidget(self.hotkey_edit)
        self.lbl_alt = QLabel("")
        self.lbl_alt.setStyleSheet("color: %s; font-size: 12px;" % theme.WARN)
        self.lbl_alt.setWordWrap(True)
        self.lbl_alt.hide()
        body.addWidget(self.lbl_alt)
        body.addWidget(self._hint("点击输入框后直接按下组合键，需包含 Ctrl / Alt / Shift / Win 之一。"))
        body.addWidget(self._hint("别用带 Alt 的组合键：别的软件展开多级菜单或下拉框时，"
                                 "Alt 一按下菜单就会自动收起，截不到里面的内容。"
                                 "改用 Ctrl+Shift+字母 即可。"))
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: %s; font-size: 12px;" % theme.DANGER)
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        body.addWidget(self.lbl_error)

        root.addStretch(1)

        # ---------------- 按钮 ----------------
        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.btn_reset = QPushButton("恢复默认")
        self.btn_reset.clicked.connect(self._restore_defaults)
        btns.addWidget(self.btn_reset)
        btns.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)
        self.btn_ok = QPushButton("保存")
        self.btn_ok.setObjectName("primary")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)

        self._on_hotkey_changed(self.hotkey_edit.value())

    # ---------- 快捷键相关提示 ----------
    def _on_hotkey_changed(self, value: str):
        """含 Alt 的组合键截不到多级菜单，当场在界面上说清楚（不是一闪而过的提示）。"""
        if contains_alt(value):
            key = value.split("+")[-1] or "S"
            self.lbl_alt.setText(
                "「%s」里有 Alt：截不到展开着的多级菜单和下拉框，"
                "建议改用 Ctrl+Shift+%s 这类不含 Alt 的组合。" % (value, key))
            self.lbl_alt.show()
        else:
            self.lbl_alt.hide()
            self.lbl_alt.setText("")

    # ---------- 组件 ----------
    def _card(self, title: str, parent_layout) -> QVBoxLayout:
        card = QFrame(self)
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(7)
        label = QLabel(title, card)
        label.setObjectName("sectionTitle")
        lay.addWidget(label)
        lay.addSpacing(1)
        parent_layout.addWidget(card)
        return lay

    def _hint(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("hint")
        lbl.setWordWrap(True)
        return lbl

    # ---------- 校验 ----------
    def _show_error(self, msg: str):
        self.lbl_error.setText(msg)
        self.lbl_error.show()

    def _clear_error(self):
        self.lbl_error.hide()
        self.lbl_error.setText("")
        self.lbl_auto_error.hide()
        self.lbl_auto_error.setText("")

    def _read_form(self):
        hotkey = self.hotkey_edit.value().strip()
        if self.hotkey_edit._recording:
            self.hotkey_edit.stop_recording()
            hotkey = self.hotkey_edit.value().strip()
        return {
            "hide_self": self.chk_hide.isChecked(),
            "close_action": "exit" if self.rb_exit.isChecked() else "tray",
            "auto_start": self.chk_auto.isChecked(),
            "hotkey": hotkey,
        }

    def _restore_defaults(self):
        self._clear_error()
        self.chk_hide.setChecked(bool(DEFAULTS["hide_self"]))
        if DEFAULTS["close_action"] == "exit":
            self.rb_exit.setChecked(True)
        else:
            self.rb_tray.setChecked(True)
        self.chk_auto.setChecked(bool(DEFAULTS["auto_start"]))
        self.hotkey_edit.set_value(DEFAULTS["hotkey"])

    def accept(self):
        self._clear_error()
        values = self._read_form()

        if not values["hotkey"]:
            self._show_error("请设置一个截图快捷键")
            self.hotkey_edit.setFocus()
            return

        ok, msg = self._try_apply_hotkey(values["hotkey"])
        if not ok:
            self._show_error(msg or "该快捷键不可用，请重新设置")
            self.hotkey_edit.setProperty("invalid", "true")
            repolish(self.hotkey_edit)
            self.hotkey_edit.setFocus()
            return

        self.hotkey_edit.setProperty("invalid", "false")
        repolish(self.hotkey_edit)

        # 开机启动项：真正写注册表，失败就把原因留在界面上，不静默吞掉
        ok, msg = autostart.apply(bool(values["auto_start"]))
        if not ok:
            self.lbl_auto_error.setText(msg or "开机启动设置失败，请稍后重试。")
            self.lbl_auto_error.show()
            return

        for k, v in values.items():
            self.cfg.set(k, v)
        self.cfg.save()
        super().accept()
