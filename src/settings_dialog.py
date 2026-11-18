# -*- coding: utf-8 -*-
"""设置对话框：截图行为、关闭行为、开机启动、全局快捷键。"""
import datetime
import os

from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QRadioButton, QToolButton, QVBoxLayout,
)

import icons
import theme
import update_log
from app_config import APP_NAME, APP_VERSION, DEFAULTS, as_bool, as_choice
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

# 录完组合键后多久去探测「有没有被别的程序占用」。
# 用户要求"设置完 2 秒内给结果"，这里 0.3 秒就查，留足余量。
HOTKEY_PROBE_DELAY_MS = 300


def hotkey_state_text(ok: bool, sequence: str, message: str = "") -> str:
    """录完快捷键后那一行状态文案（纯函数，方便测试）。"""
    seq = (sequence or "").strip()
    if ok:
        return "「%s」可以使用。" % seq if seq else ""
    return message or ("「%s」不可用，请更换其他组合。" % seq if seq else "")


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
    check_requested = pyqtSignal()

    def __init__(self, cfg, try_apply_hotkey, parent=None, update_info=None,
                 probe_hotkey=None):
        super().__init__(parent)
        self.cfg = cfg
        self._try_apply_hotkey = try_apply_hotkey
        # 只探测不改状态的接口：录完组合键立刻用来判断有没有被别的程序占用
        self._probe_hotkey = probe_hotkey
        self._update_info = update_info
        self._checking = False
        # 构造过程中会调一次 _on_hotkey_changed，那时不该去探测（避免一开设置就弹状态）
        self._ready = False
        # 点了「发现新版本」箭头：关掉设置、交给主程序去开更新窗口
        self.wants_update = False
        # 点过「恢复默认」：保存时连界面上看不到的设置项（笔色、字号、粗体）一起回默认
        self._reset_extras = False

        self.setWindowTitle("设置 - %s" % APP_NAME)
        self.setWindowIcon(QIcon("assets/app.ico"))
        self.setStyleSheet(theme.dialog_qss())
        self.setMinimumWidth(500)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 14)
        root.setSpacing(10)

        # ---------------- 截图行为 ----------------
        body = self._card("截图", root)
        self.chk_hide = QCheckBox("截图时隐藏「%s」窗口" % APP_NAME)
        self.chk_hide.setChecked(as_bool(cfg.get("hide_self"), DEFAULTS["hide_self"]))
        body.addWidget(self.chk_hide)
        body.addWidget(self._hint("截图瞬间自动隐藏本软件窗口，截图里不会出现软件界面。"))

        # ---------------- 关闭按钮 ----------------
        body = self._card("点击窗口关闭按钮时", root)
        self.rb_tray = QRadioButton("隐藏到托盘")
        self.rb_exit = QRadioButton("直接退出程序")
        if as_choice(cfg.get("close_action"), ("tray", "exit"),
                     DEFAULTS["close_action"]) == "exit":
            self.rb_exit.setChecked(True)
        else:
            self.rb_tray.setChecked(True)
        body.addWidget(self.rb_tray)
        body.addWidget(self.rb_exit)
        body.addWidget(self._hint("隐藏到托盘：关闭窗口后程序继续在桌面右下角托盘区运行，双击托盘图标可重新打开窗口。"))

        # ---------------- 开机启动 ----------------
        body = self._card("开机启动", root)
        self.chk_auto = QCheckBox("开机时自动启动「%s」" % APP_NAME)
        self.chk_auto.setChecked(as_bool(cfg.get("auto_start"), DEFAULTS["auto_start"]))
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
        body.addWidget(self._hint("在输入框内直接按组合键（须含 Ctrl、Shift 或 Win）。"
                                 "不建议含 Alt：按下 Alt 会收起已展开的菜单，"
                                 "导致菜单内容无法截取。推荐 Ctrl+Shift+字母。"))
        # 录完组合键马上给结果：能不能用、被谁占用，不用等点保存才知道
        self.lbl_hotkey_state = QLabel("")
        self.lbl_hotkey_state.setStyleSheet("color: %s; font-size: 12px;" % theme.TEXT_SUB)
        self.lbl_hotkey_state.setWordWrap(True)
        self.lbl_hotkey_state.hide()
        body.addWidget(self.lbl_hotkey_state)
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: %s; font-size: 12px;" % theme.DANGER)
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        body.addWidget(self.lbl_error)

        # 探测用定时器：录键时手一停就查，节流到 0.3 秒，不会每敲一下都去问系统
        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.setInterval(HOTKEY_PROBE_DELAY_MS)
        self._probe_timer.timeout.connect(self._probe_now)

        # ---------------- 版本与更新 ----------------
        body = self._card("版本与更新", root)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.lbl_version = QLabel("当前版本 %s" % APP_VERSION)
        self.lbl_version.setObjectName("versionText")
        row.addWidget(self.lbl_version)

        # 有新版本时，版本号后面亮出绿箭头
        self.btn_update = QToolButton(self)
        self.btn_update.setObjectName("updateBtn")
        self.btn_update.setIcon(QIcon(icons.render("update", 20)))
        self.btn_update.setIconSize(QSize(20, 20))
        self.btn_update.setFixedSize(24, 24)
        self.btn_update.setCursor(Qt.PointingHandCursor)
        self.btn_update.setFocusPolicy(Qt.NoFocus)
        self.btn_update.setToolTip("发现新版本，点击查看")
        self.btn_update.clicked.connect(self._open_update)
        self.btn_update.hide()
        row.addWidget(self.btn_update)

        row.addStretch(1)
        self.btn_check = QPushButton("立即检查", self)
        self.btn_check.setObjectName("linkBtn")
        self.btn_check.setCursor(Qt.PointingHandCursor)
        self.btn_check.setFocusPolicy(Qt.NoFocus)
        self.btn_check.clicked.connect(self._request_check)
        row.addWidget(self.btn_check)
        body.addLayout(row)

        # 「自动检查更新」单独一行：挤在上面那一行时，窗口略窄就会被压扁甚至
        # 挤出可视区，看起来就像「没勾上」。单独一行之后任何宽度都完整可见。
        self.chk_update = QCheckBox("自动检查更新")
        self.chk_update.setChecked(as_bool(cfg.get("check_update"),
                                          DEFAULTS["check_update"]))
        chk_row = QHBoxLayout()
        chk_row.setContentsMargins(0, 4, 0, 0)
        chk_row.addWidget(self.chk_update)
        chk_row.addStretch(1)
        body.addLayout(chk_row)
        body.addWidget(self._hint("软件每次启动时检查一次，常驻托盘期间每 12 小时检查一次。"
                                 "检测到新版本后会在界面中提示，点击「立即更新」可自动下载、"
                                 "静默安装并重新启动。检查失败时可在「诊断与日志」中查看原因。"))
        # 让「到底有没有在查、查出什么」都看得见 —— 怀疑没提示时先看这一行
        self.lbl_last = self._hint(self._last_check_text(cfg))
        body.addWidget(self.lbl_last)

        if update_info is not None:
            self._show_update_badge(update_info)

        # ---------------- 诊断与日志 ----------------
        # 日志早就不只记更新了：截图会话、工具条兜底、剪贴板回读、崩溃栈都在里面，
        # 挂在「版本与更新」下面会让人以为只有更新的事才需要它。
        body = self._card("诊断与日志", root)
        body.addWidget(self._hint("记录程序功能异常、更新检查等过程。"
                                 "点击「打开日志目录」可查看日志文件，或在遇到问题时将日志文件提交给开发者。"
                                 ))
        log_row = QHBoxLayout()
        log_row.setSpacing(10)
        self.btn_log = QPushButton("打开日志目录", self)
        self.btn_log.setCursor(Qt.PointingHandCursor)
        self.btn_log.setFocusPolicy(Qt.NoFocus)
        self.btn_log.clicked.connect(self._open_log)
        log_row.addWidget(self.btn_log)
        self.lbl_log_usage = QLabel(update_log.usage_text(), self)
        self.lbl_log_usage.setStyleSheet("color: %s; font-size: 12px;" % theme.TEXT_SUB)
        log_row.addWidget(self.lbl_log_usage)
        log_row.addStretch(1)
        body.addLayout(log_row)
        self._refresh_usage()

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
        # 版本号那一行元素多（版本号 + 绿箭头 + 立即检查 + 查看日志 + 复选框）：
        # 窗口窄到一定程度会把复选框挤出可视区，看起来就像「没勾选」。
        # 这里按内容算一次自然宽度当最小宽度，字号变大时也跟着变。
        self.setMinimumWidth(max(500, self.sizeHint().width()))
        self._ready = True

    # ---------- 快捷键相关提示 ----------
    def _on_hotkey_changed(self, value: str):
        """含 Alt 的组合键无法截取展开的多级菜单，当场在界面上说明（不是一闪而过的提示）。"""
        if contains_alt(value):
            key = value.split("+")[-1] or "S"
            self.lbl_alt.setText(
                "「%s」包含 Alt：按下 Alt 会收起已展开的菜单和下拉框，"
                "无法截取其内容。建议改用 Ctrl+Shift+%s 等不含 Alt 的组合。"
                % (value, key))
            self.lbl_alt.show()
        else:
            self.lbl_alt.hide()
            self.lbl_alt.setText("")

        # 换了组合，上一条「已被占用」的报错就过期了，先清掉
        self.lbl_error.hide()
        self.lbl_error.setText("")

        if not self._ready:
            return                      # 刚打开设置时不必自己去查当前这把键

        self._probe_timer.stop()
        value = (value or "").strip()
        if not value or self._probe_hotkey is None:
            self._set_hotkey_state("")
            return
        # 先给一句「正在检查」，0.3 秒后换成真实结果 —— 用户不用等点保存
        self._set_hotkey_state("正在检查「%s」是否可用…" % value, theme.TEXT_SUB)
        self._probe_timer.start()

    def _probe_now(self):
        """真正去问系统：这把组合键现在能不能注册。"""
        if self._probe_hotkey is None:
            return
        value = self.hotkey_edit.value().strip()
        if not value:
            self._set_hotkey_state("")
            return
        try:
            ok, msg = self._probe_hotkey(value)
        except Exception as e:                     # 探测本身出错不能把设置弄崩
            self._set_hotkey_state("无法检查快捷键：%s" % e, theme.WARN)
            return
        self._set_hotkey_state(hotkey_state_text(ok, value, msg),
                               theme.SUCCESS if ok else theme.DANGER)
        self.hotkey_edit.setProperty("invalid", "false" if ok else "true")
        repolish(self.hotkey_edit)

    def _set_hotkey_state(self, text: str, color: str = ""):
        if not text:
            self.lbl_hotkey_state.hide()
            self.lbl_hotkey_state.setText("")
            return
        self.lbl_hotkey_state.setStyleSheet(
            "color: %s; font-size: 12px;" % (color or theme.TEXT_SUB))
        self.lbl_hotkey_state.setText(text)
        self.lbl_hotkey_state.show()

    # ---------- 新版本提示 ----------
    def _show_update_badge(self, info):
        ver = (getattr(info, "version", "") or "").strip()
        self.btn_update.setToolTip("发现新版本 %s，点击查看" % ver if ver
                                  else "发现新版本，点击查看")
        self.btn_update.show()

    def set_update_info(self, info):
        """主程序查到（或确认没有）新版本时，设置页当场跟着变，不用关掉重开。"""
        self._update_info = info
        if info is None:
            self.btn_update.hide()
            self.btn_update.setToolTip("发现新版本")
        else:
            self._show_update_badge(info)
        self._refresh_last_check()

    def _request_check(self):
        """点「立即检查」：先进入检查中状态，结果由主程序回填。"""
        if self._checking:
            return
        self.set_checking(True)
        self.check_requested.emit()

    def _refresh_usage(self):
        """占用写在小字里：日志会一直写，用户有权知道它有多大、有没有上限。"""
        try:
            u = update_log.usage()
            self.lbl_log_usage.setText(update_log.usage_text())
            self.lbl_log_usage.setToolTip(
                "运行日志 %.0f KB\n崩溃记录 %.0f KB\n兜底截图 %.0f KB（%d 张）\n"
                "日志只保留最近 240 行；兜底截图只留最近 %d 张、最多 %d MB。"
                % (u["log"] / 1024.0, u["crash"] / 1024.0,
                   u["shots"] / 1024.0, u["shot_count"],
                   update_log.SHOT_KEEP, update_log.SHOT_MAX_BYTES // (1024 * 1024)))
        except Exception:
            pass

    def _open_log(self):
        """打开日志目录并选中日志文件。

        日志分两个：update.log（运行、更新、每次截图会话的完整流程）和
        crash.log（崩溃与异常栈，没出过事就没有这个文件）。以前只打开
        update.log，崩溃记录和兜底截图还得自己去用户目录翻，所以改成
        打开所在目录 —— 三个东西并排放着，一眼看得全。
        """
        folder, target = update_log.open_target()
        if not os.path.isdir(folder):
            QMessageBox.information(self, "还没有日志",
                                    "程序运行后才会生成日志文件。\n"
                                    "目录：%s" % folder)
            return
        try:
            if target:
                import subprocess
                subprocess.Popen('explorer /select,"%s"' % os.path.normpath(target))
            else:
                os.startfile(folder)        # noqa: S606  Windows 专用
        except Exception as e:
            QMessageBox.warning(self, "打不开日志",
                                "请手动打开这个目录：\n%s\n\n%s" % (folder, e))
        self._refresh_usage()

    def set_checking(self, on: bool):
        self._checking = bool(on)
        self.btn_check.setEnabled(not on)
        self.btn_check.setText("检查中…" if on else "立即检查")
        if on:
            self.lbl_last.setText("正在检查更新，请稍候…")
        else:
            self._refresh_last_check()

    def set_check_result(self, result_text: str = ""):
        """一次检查结束：退出「检查中」并刷新「上次检查」那一行。"""
        self._checking = False
        self.btn_check.setEnabled(True)
        self.btn_check.setText("立即检查")
        self._refresh_last_check(result_text)

    def _refresh_last_check(self, result_text=None):
        self.lbl_last.setText(self._last_check_text(self.cfg, result_text))

    def _open_update(self):
        """关掉设置，交给主程序打开更新窗口（设置里的改动不保存）。"""
        self.wants_update = True
        self.reject()

    # ---------- 组件 ----------
    def _card(self, title: str, parent_layout) -> QVBoxLayout:
        card = QFrame(self)
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 10, 16, 12)
        lay.setSpacing(6)
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

    @staticmethod
    def _last_check_text(cfg, result_text=None) -> str:
        """上次检查更新的时间 + 结果，让用户能确认自动检查到底跑没跑、查出了什么。"""
        try:
            ts = int(cfg.get("update_last_check") or 0)
        except (TypeError, ValueError):
            ts = 0
        if result_text is None:
            result_text = str(cfg.get("update_last_result") or "").strip()
        if ts <= 0:
            base = "上次检查：暂无记录"
        else:
            dt = datetime.datetime.fromtimestamp(ts)
            today = datetime.date.today()
            if dt.date() == today:
                when = "今天 %s" % dt.strftime("%H:%M")
            elif dt.date() == today - datetime.timedelta(days=1):
                when = "昨天 %s" % dt.strftime("%H:%M")
            else:
                when = dt.strftime("%Y-%m-%d %H:%M")
            base = "上次检查：%s" % when
        result_text = str(result_text or "").strip()
        return "%s · %s" % (base, result_text) if result_text else base

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
            "check_update": self.chk_update.isChecked(),
            "hotkey": hotkey,
        }

    def _restore_defaults(self):
        """所有设置项回到出厂值（保存后才生效）。

        界面上能改的 5 项当场回填；界面上没有的（笔色、字号、粗体）先记下来，
        点保存时一起写回默认，保证「恢复默认」确实是全部恢复，而不只是看得见的那几项。
        """
        self._clear_error()
        self._reset_extras = True
        self.chk_hide.setChecked(bool(DEFAULTS["hide_self"]))
        if DEFAULTS["close_action"] == "exit":
            self.rb_exit.setChecked(True)
        else:
            self.rb_tray.setChecked(True)
        self.chk_auto.setChecked(bool(DEFAULTS["auto_start"]))
        self.chk_update.setChecked(bool(DEFAULTS["check_update"]))
        self.hotkey_edit.set_value(DEFAULTS["hotkey"])

    def accept(self):
        self._probe_timer.stop()          # 别让延迟的探测把保存时的报错覆盖掉
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

        if self._reset_extras:
            # 先把界面上看不到的设置项回默认，再写入当前表单的值（用户若在
            # 「恢复默认」之后又改了某一项，以他最后的选择为准）
            self.cfg.reset_settings()
        for k, v in values.items():
            self.cfg.set(k, v)
        self.cfg.save()
        super().accept()
