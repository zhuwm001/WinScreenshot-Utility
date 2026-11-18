# -*- coding: utf-8 -*-
"""我爱截图 —— 程序入口与总控。"""
import os
import sys
import time

import qt_env  # 必须早于 PyQt5：先把 Qt 平台插件目录指好，否则会弹 no Qt platform plugin

qt_env.setup()

from PyQt5.QtCore import QObject, QRect, Qt, QTimer
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QSystemTrayIcon

import theme
import autostart
import update_log
from app_config import APP_NAME, APP_VERSION, as_bool, config, config_dir
from hotkey import HotkeyManager, normalize_sequence
from install_notice import InstallNotice
from main_window import MainWindow
from overlay import CaptureSession
from paths import asset
from pin_window import PinWindow
from screenshot import capture_desktop, set_process_dpi_awareness
from settings_dialog import SettingsDialog
from toast import Toast
from update import (UpdateChecker, clear_pending, cleanup_installers,
                    install_dir_writable, launch_silent_install, parse_version,
                    read_pending, running_exe, version_from_installer,
                    write_pending)
from update_dialog import MODE_ERROR, MODE_LATEST, MODE_NEW, UpdateDialog
from update_log import log as ulog

SERVER_NAME = "WoAiJieTu.SingleInstance.v1"

# 静默安装时提示卡片停留多久。安装程序在进程退出后还要等 3 秒才开始，
# 卡片留 2.8 秒刚好让两边接上，中间不留空档。
INSTALL_NOTICE_MS = 2800

# crash.log 的文件句柄，必须挂在模块级活到进程结束（faulthandler 用它输出）
_CRASH_FILE = None

# 启动后多久去问 GitHub（留出时间给界面先起来，但尽量在用户点开设置前问完）
UPDATE_DELAY_MS = 2000
# 常驻期间两次自动检查之间至少隔多久（启动、手动检查都不受这个限制）
UPDATE_INTERVAL = 12 * 3600
# 运行期间多久看一眼「该不该查了」。托盘程序可能几天不退出，只在启动时查
# 就永远等不到新版本；这里 10 分钟醒一次，真正请求仍受 UPDATE_INTERVAL 限制。
UPDATE_POLL_MS = 10 * 60 * 1000

# 一次更新检查的来源。要不要真的去请求，全部由 check_allowed() 判断。
# 只有三种：进程启动、常驻到点、用户手动。托盘里再打开一次（第二个进程被
# 合并进已有进程）不算 —— 那种「打开」不是新会话，查了也是白查。
CHECK_STARTUP = "startup"      # 进程刚起来
CHECK_TIMER = "timer"          # 常驻期间到点自动查
CHECK_MANUAL = "manual"        # 用户主动点「检查更新 / 立即检查」


def update_due(last_ts, now=None, interval=UPDATE_INTERVAL) -> bool:
    """常驻期间是否到了该自动检查的时候。

    只用于定时器那一路；启动那一次走 CHECK_STARTUP，不受这里限制。
    """
    try:
        last_ts = int(last_ts or 0)
    except (TypeError, ValueError):
        last_ts = 0
    if last_ts <= 0:
        return True
    return (now if now is not None else time.time()) - last_ts >= interval


def check_allowed(trigger, last_ts=0, now=None, enabled=True) -> bool:
    """这一次要不要真的去问 GitHub —— 启动 / 定时 / 手动共用这套判断。

    规则（三个入口一视同仁，不再各写一套）：
      * 关掉「自动检查更新」后，自动的两条路都不查；手动仍然照查
      * 启动：每次启动都查一次，不看节流（否则「刚查过 -> 重启」就永远不提示）
      * 定时：距上次检查满 12 小时才查
      * 手动：随时查
    """
    if trigger == CHECK_MANUAL:
        return True
    if not enabled:
        return False
    now = time.time() if now is None else now
    if trigger == CHECK_TIMER:
        return update_due(last_ts, now=now)
    return True                 # CHECK_STARTUP


def short_reason(text: str, limit: int = 26) -> str:
    """把一长串错误压成一句话，塞进设置页那一行里。"""
    t = (text or "").strip()
    for tail in ("。", ".", "；", ";"):
        t = t.rstrip(tail)
    if len(t) <= limit:
        return t
    return t[:limit - 1] + "…"


def check_result_text(kind: str, version: str = "", reason: str = "") -> str:
    """写进配置、显示在设置页「上次检查」后面的那句结果（纯函数）。"""
    if kind == "found":
        ver = (version or "").strip()
        return "发现新版本 %s" % ver if ver else "发现新版本"
    if kind == "latest":
        return "已是最新版本"
    if kind == "failed":
        why = short_reason(reason)
        return "检查失败：%s" % why if why else "检查失败"
    return ""


def update_outcome(pending, current) -> str:
    """上一次安装的结果：'done' / 'failed' / ''（没有回执或版本不明）。

    判断依据只有一个 —— 现在跑的版本有没有达到当初要装的版本。
    所以即使安装过程被杀软拦掉、被用户取消、目录不可写，这里都会如实反映。
    """
    if not pending or not isinstance(pending, dict):
        return ""
    target = str(pending.get("version") or "").strip()
    if not target:
        return ""
    return "done" if parse_version(current) >= parse_version(target) else "failed"


def tray_tip(hotkey: str):
    """隐藏到托盘后的提示文案（纯函数，方便测试）。"""
    hk = (hotkey or "").strip()
    if hk:
        text = ("程序仍在后台运行，截图快捷键 %s 可以照常使用；"
                "双击托盘图标可重新打开窗口。" % hk)
    else:
        text = "程序仍在后台运行，双击托盘图标可重新打开窗口。"
    return "已隐藏到托盘", text


def acquire_single_instance():
    """已有实例在运行时唤醒它并退出；否则返回监听中的 server。"""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(250):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return None

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    if not server.listen(SERVER_NAME):
        return None
    return server


class AppController(QObject):
    def __init__(self, app: QApplication, server: QLocalServer):
        super().__init__()
        self.app = app
        self.server = server
        self.server.newConnection.connect(self._on_second_instance)

        self._restore_main = False
        self.overlay = None
        self._capture_guard = False
        self._copy_note = ""            # 剪贴板写不进去时的落盘路径（用于提示）
        self._hide_rect = QRect()
        self._checker = None
        self._update_dlg = None
        self._settings_dlg = None
        self._check_trigger = CHECK_TIMER
        # 已经为哪个版本弹过「发现新版本」窗口；用户点过「稍后」就不再反复弹
        self._prompted_version = ""
        # 已经查到但还没安装的新版本：主界面和设置页靠它亮绿箭头
        self._available_update = None
        # 常驻托盘时也要持续发现新版本，不能只靠「下次启动」
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(UPDATE_POLL_MS)
        self._update_timer.timeout.connect(self._schedule_update_check)

        self.win = MainWindow(config.get("hotkey"))
        self.win.capture_requested.connect(self.start_capture)
        self.win.settings_requested.connect(self.open_settings)
        self.win.update_requested.connect(self.show_update)
        self.win.hide_requested.connect(self.hide_to_tray)
        self.win.quit_requested.connect(self.quit_app)
        self.win.close_requested.connect(self.on_main_close)

        self.hotkey = HotkeyManager(app)
        self.hotkey.activated.connect(lambda: self.start_capture(from_hotkey=True))

        self._build_tray()

    # ------------------------------------------------------------ 启动
    def start(self, silent: bool = False):
        self.win.center_on_screen()
        if not silent:
            self.win.show_and_raise()

        ok, msg = self.hotkey.register(config.get("hotkey"))
        if not ok:
            if not self.win.isVisible():
                self.win.show_and_raise()
            Toast.show_toast("快捷键不可用",
                             "%s\n请到「设置」里重新设置一个快捷键。" % (msg or ""),
                             kind="warn", timeout=3000)
            self.open_settings()
        self._refresh_tray_menu()
        self._sync_autostart()
        self._startup_update_check()
        self._update_timer.start()
        QTimer.singleShot(1200, self._notify_update_result)

    def _sync_autostart(self):
        """校正注册表里的启动项，与设置里的开关保持一致。"""
        on = as_bool(config.get("auto_start"), False)
        try:
            if on and not autostart.is_enabled():
                # 用户可能在任务管理器里自行关掉了，尊重这个选择
                config.set("auto_start", False)
                config.save()
            elif on and autostart.current_command() != autostart.launch_command():
                autostart.apply(True)      # 程序被移动或重装过，刷新路径
            elif not on and autostart.is_enabled():
                autostart.apply(False)
        except Exception:
            pass

    # ------------------------------------------------------------ 托盘
    def _build_tray(self):
        ico = QIcon(asset("app.ico"))
        if ico.availableSizes() == []:
            import icons
            ico = icons.render_icon("camera", 32)
        self.tray = QSystemTrayIcon(ico, self)
        self.tray.setToolTip("%s %s" % (APP_NAME, APP_VERSION))
        self.tray.setContextMenu(QMenu())
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self._refresh_tray_menu()

    def _refresh_tray_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background: #FFFFFF; border: 1px solid #E6EAF2; border-radius: 9px;
                    padding: 6px; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
            QMenu::item { padding: 8px 26px 8px 16px; border-radius: 6px; color: #1F2330; }
            QMenu::item:selected { background: #F2F6FF; color: #4A86FF; }
            QMenu::separator { height: 1px; background: #EEF1F7; margin: 5px 8px; }
        """)
        hk = config.get("hotkey") or "未设置"
        act_capture = menu.addAction("开始截图          %s" % hk)
        act_capture.triggered.connect(self.start_capture)

        act_show = menu.addAction("打开主界面")
        act_show.triggered.connect(self.show_main)

        act_settings = menu.addAction("设置…")
        act_settings.triggered.connect(self.open_settings)

        menu.addSeparator()
        act_update = menu.addAction("检查更新…")
        if self._available_update is not None:
            ver = (getattr(self._available_update, "version", "") or "").strip()
            act_update.setText("发现新版本 %s，点击更新…" % ver if ver
                               else "发现新版本，点击更新…")
        act_update.triggered.connect(
            lambda: self.request_update_check(CHECK_MANUAL))

        menu.addSeparator()
        act_quit = menu.addAction("退出")
        act_quit.triggered.connect(self.quit_app)

        self.tray.setContextMenu(menu)
        self._tray_menu = menu

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_main()

    def _on_second_instance(self):
        conn = self.server.nextPendingConnection()
        if conn is not None:
            conn.readyRead.connect(conn.readAll)
            conn.disconnected.connect(conn.deleteLater)
        # 已有进程被唤醒（用户又点了一次图标）：只是把窗口叫出来，不查更新。
        # 真正的「启动」是进程重开那一次，那条路在 start() 里查。
        self.show_main()

    # ------------------------------------------------------------ 窗口
    def show_main(self):
        if not self.win.isVisible():
            self.win.center_on_screen()
        self.win.show_and_raise()

    def hide_to_tray(self):
        self.win.hide()
        # 每次隐藏都给提示：托盘程序可能几天不重启，只提示第一次等于没提示
        title, text = tray_tip(config.get("hotkey"))
        Toast.show_toast(title, text, kind="info", timeout=3200)

    def on_main_close(self):
        if config.get("close_action") == "exit":
            self.quit_app()
        else:
            self.hide_to_tray()

    def quit_app(self):
        ulog("退出程序")
        try:
            self.hotkey.close()
        except Exception:
            pass
        self.tray.hide()
        self.win.hide()
        QApplication.quit()
        # 兜底：托盘程序「退出」必须真的退出。万一还有隐藏窗口或没退干净的事件
        # 循环把 quit() 吞了，进程就会赖在后台占着热键和单实例 —— 用户再双击
        # 图标只会唤醒它、不会走启动检查，看上去就像「重开了却不查更新」。
        QTimer.singleShot(3000, self._force_exit)

    def _force_exit(self):
        ulog("退出兜底：3 秒内没有正常结束，强制退出")
        os._exit(0)

    # ------------------------------------------------------------ 截图
    def start_capture(self, from_hotkey: bool = False):
        if self._capture_guard or self.overlay is not None:
            return
        self._capture_guard = True
        QTimer.singleShot(120, self._release_guard)

        # 1) 先抓屏，再去动任何窗口。
        #    下拉框、右键菜单、点了按钮才出现的面板，一旦被抢走焦点就会自己消失。
        #    钩子把组合键"吞掉"了，前台程序根本收不到那几个键，菜单不会因为
        #    截图快捷键而收起（前提是快捷键里不含 Alt —— Alt 一按下，
        #    系统层面就会把别人的菜单收起来，这点在设置里已提示用户）。
        #    逐屏抓：两块屏缩放比例不同时，这样才不会有一块屏是黑的。
        desk = capture_desktop()

        self._restore_main = self.win.isVisible()
        self._hide_rect = QRect()
        if config.get("hide_self") and self.win.isVisible():
            # 自己的窗口要先藏起来，否则会被截进去；但画面已经拍好，
            # 只需要等它真正消失后把那一小块区域重抓一次补回去。
            self._hide_rect = QRect(self.win.frameGeometry())
            self.win.hide()
            # 等窗口真正从合成器上撤走（约两帧），再只补抓这一块
            QTimer.singleShot(120, lambda: self._open_overlay(desk))
        else:
            QTimer.singleShot(0, lambda: self._open_overlay(desk))

    def _release_guard(self):
        self._capture_guard = False
        self._copy_note = ""            # 剪贴板写不进去时的落盘路径（用于提示）

    def _open_overlay(self, desk=None):
        if desk is not None and not self._hide_rect.isNull():
            desk.patch(self._hide_rect)
        self._hide_rect = QRect()

        self.overlay = CaptureSession(desk,
                                      config.get("pen_color"),
                                      config.get("text_size"),
                                      config.get("text_bold"))
        self.overlay.finished.connect(self._on_capture_done)
        self.overlay.copy_fallback.connect(self._on_copy_fallback)
        self.overlay.cancelled.connect(self._on_capture_cancelled)
        self.overlay.pinned.connect(self._on_pinned)
        self.overlay.closed.connect(self._on_overlay_destroyed)
        self.overlay.show_overlay()

    def _on_overlay_destroyed(self, *_):
        self.overlay = None

    def _on_copy_fallback(self, path):
        # 剪贴板被别的程序占着、写不进去时改存文件；这里把路径记下来给提示用
        self._copy_note = path

    def _on_capture_done(self, image):
        self._persist_text_style()
        self.overlay = None
        self._restore_main_window()
        note = getattr(self, "_copy_note", "")
        self._copy_note = ""
        if note and note != "?":
            Toast.show_toast("已存为图片文件", "剪贴板被其他程序占用，图片保存在 %s" % note,
                             kind="info", timeout=6000)
        elif note == "?":
            Toast.show_toast("复制失败", "剪贴板被其他程序占用，图片也未能保存。",
                             kind="info", timeout=6000)
        else:
            Toast.show_toast("已复制到剪贴板", "可在其他窗口中按 Ctrl+V 粘贴。",
                             kind="check", timeout=3000)

    def _on_capture_cancelled(self):
        self._persist_text_style()
        self.overlay = None
        self._restore_main_window()

    def _on_pinned(self, image, screen_pos):
        self._persist_text_style()
        self.overlay = None
        self._restore_main_window()
        pin = PinWindow(image, screen_pos, self._screen_dpr_at(screen_pos))
        pin.show()

    def _persist_text_style(self):
        """记住上一次用过的字号/粗细，下次截图直接沿用。"""
        ov = self.overlay
        if ov is None:
            return
        try:
            size, bold = ov.text_style()
        except RuntimeError:
            return
        if config.get("text_size") != size or bool(config.get("text_bold")) != bool(bold):
            config.set("text_size", int(size))
            config.set("text_bold", bool(bold))
            config.save()

    @staticmethod
    def _screen_dpr() -> float:
        screen = QApplication.primaryScreen()
        return float(screen.devicePixelRatio()) if screen else 1.0

    @staticmethod
    def _screen_dpr_at(pos) -> float:
        """这块屏幕自己的缩放比例 —— 贴图窗口要按它换算回逻辑尺寸。"""
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        return float(screen.devicePixelRatio()) if screen else 1.0

    def _restore_main_window(self):
        # 恢复主界面但不抢焦点，方便用户直接粘贴到其他窗口
        if self._restore_main and not self.win.isVisible():
            self.win.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.win.show()
        self._restore_main = False

    # ------------------------------------------------------------ 更新
    def _startup_update_check(self):
        """进程起来后问一次，**不看** 12 小时节流。

        节流时间戳在每次检查时都会刷新（包括用户手动点的那次），如果启动也
        看它，就会出现「刚手动查过 -> 重启 -> 明明有新版本却不提示」。
        启动是低频事件，多问一次的成本可以忽略。
        """
        QTimer.singleShot(UPDATE_DELAY_MS,
                          lambda: self.request_update_check(CHECK_STARTUP))

    def _schedule_update_check(self):
        """常驻期间看一眼「该不该查了」；真正请求仍受 12 小时节流限制。"""
        self.request_update_check(CHECK_TIMER)

    def request_update_check(self, trigger=CHECK_TIMER) -> bool:
        """所有更新检查的唯一入口（启动 / 定时 / 手动）。

        判断「这次要不要真的去问」统一走 check_allowed()，不会出现某条路
        绕过节流、或者查完了却忘了刷新「上次检查」时间的情况。
        每次的决定都写进 update.log，事后不用靠猜。
        """
        enabled = as_bool(config.get("check_update"), True)
        if not check_allowed(trigger, config.get("update_last_check"),
                             enabled=enabled):
            if trigger != CHECK_TIMER:       # 定时器每 10 分钟问一次，别刷屏
                ulog("跳过检查（%s）：自动检查已关闭或没到时间" % trigger)
            return False
        if self._checker is not None:
            ulog("跳过检查（%s）：上一次还没结束" % trigger)
            if trigger == CHECK_MANUAL:
                Toast.show_toast("正在检查更新", "上一次检查还没结束，请稍候…",
                                 kind="info", timeout=1800)
            return False                     # 上一次还没回结果，别并发
        self._check_trigger = trigger
        # 先记时间：失败了也别每次开机都重试，到下个周期再来
        config.set("update_last_check", int(time.time()))
        config.save()
        ulog("触发检查（%s）" % trigger)
        dlg = self._settings_dialog()
        if dlg is not None:
            dlg.set_checking(True)
        self._checker = UpdateChecker(self)
        self._checker.found.connect(self._on_update_found)
        self._checker.latest.connect(self._on_update_latest)
        self._checker.failed.connect(self._on_update_failed)
        self._checker.check(APP_VERSION)
        if trigger == CHECK_MANUAL:
            Toast.show_toast("正在检查更新", "正在获取最新版本信息…",
                             kind="info", timeout=2000)
        return True

    def _drop_checker(self):
        checker = self._checker
        self._checker = None
        if checker is not None:
            checker.deleteLater()

    def _settings_dialog(self):
        dlg = self._settings_dlg
        if dlg is None:
            return None
        try:
            dlg.isVisible()              # 窗口已被销毁时这里会抛 RuntimeError
        except RuntimeError:
            self._settings_dlg = None
            return None
        return dlg

    def _set_update_available(self, info):
        """记住「有没有新版本」，主界面、设置页、托盘菜单都跟着它走。"""
        self._available_update = info
        self.win.set_update_available(info)
        self._refresh_tray_menu()
        dlg = self._settings_dialog()
        if dlg is not None:
            # 设置页正开着的时候查到新版本：箭头要当场亮起来，不能等关掉重开
            dlg.set_update_info(info)

    def _remember_result(self, kind: str, version: str = "", reason: str = ""):
        text = check_result_text(kind, version, reason)
        config.set("update_last_result", text)
        config.save()
        dlg = self._settings_dialog()
        if dlg is not None:
            dlg.set_check_result(text)

    def _on_update_found(self, info):
        self._drop_checker()
        ver = getattr(info, "version", "") or ""
        same = (self._available_update is not None and
                (getattr(self._available_update, "version", "") or "") == ver)
        self._set_update_available(info)
        self._remember_result("found", ver)
        if same and self._prompted_version == ver:
            # 同一个版本已经弹过一次、用户点了「稍后」：绿箭头还亮着，
            # 就别每次打开窗口都再糊他一脸弹窗了。
            return
        self._open_update_dialog(info, MODE_NEW)

    def _on_update_latest(self, version):
        self._drop_checker()
        self._set_update_available(None)
        self._remember_result("latest")
        # 自动检查安静收场，只有用户自己点的那一次才需要弹「已是最新」
        if self._check_trigger == CHECK_MANUAL:
            self._open_update_dialog(None, MODE_LATEST)

    def _on_update_failed(self, message):
        self._drop_checker()
        self._remember_result("failed", reason=message)
        if self._check_trigger == CHECK_MANUAL:
            self._open_update_dialog(None, MODE_ERROR, message)

    def _live_update_dialog(self):
        """当前那个更新窗口还能不能用；已经跟着父窗口一起关掉的就清掉。"""
        dlg = self._update_dlg
        if dlg is None:
            return None
        try:
            if dlg.isVisible():
                return dlg
        except RuntimeError:
            pass
        self._update_dlg = None
        try:
            dlg.deleteLater()
        except RuntimeError:
            pass
        return None

    def _open_update_dialog(self, info, mode, message: str = ""):
        dlg = self._live_update_dialog()
        if dlg is not None:
            dlg.raise_()
            dlg.activateWindow()
            return
        # 设置页是模态窗口，别的窗口在它开着的时候点不动 —— 所以查到新版本时
        # 把更新窗口挂到设置页下面，用户不用先关设置才能点「立即更新」。
        parent = self._settings_dialog()
        if parent is None:
            parent = self.win if self.win.isVisible() else None
        dlg = UpdateDialog(info=info, message=message, mode=mode, parent=parent)
        dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dlg.ready_to_install.connect(self._install_update)
        dlg.retry_requested.connect(self._retry_check)
        dlg.finished.connect(self._on_update_dialog_closed)
        self._update_dlg = dlg
        if mode == MODE_NEW and info is not None:
            self._prompted_version = getattr(info, "version", "") or ""
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_update_dialog_closed(self, *_):
        self._update_dlg = None

    def _retry_check(self):
        QTimer.singleShot(200, lambda: self.request_update_check(CHECK_MANUAL))

    def show_update(self):
        """点绿箭头：已经知道有新版本就直接开窗口，否则现查一次。"""
        dlg = self._live_update_dialog()
        if dlg is not None:
            dlg.raise_()
            dlg.activateWindow()
            return
        if self._available_update is not None:
            self._open_update_dialog(self._available_update, MODE_NEW)
        else:
            self.request_update_check(CHECK_MANUAL)

    def _on_settings_check(self):
        """设置页里点「立即检查」：和托盘菜单、绿箭头走同一套判断。"""
        ok = self.request_update_check(CHECK_MANUAL)
        dlg = self._settings_dialog()
        if dlg is None:
            return
        if ok or self._checker is not None:
            dlg.set_checking(True)
        else:
            dlg.set_check_result()

    def _install_update(self, installer_path: str):
        # 装之前先落回执：新版本第一次起来时靠它判断「这次到底装成了没有」
        target = version_from_installer(installer_path)
        if not target and self._update_dlg is not None:
            info = getattr(self._update_dlg, "info", None)
            target = getattr(info, "version", "") or ""
        write_pending(target, installer_path)

        # 安装目录不可写时别硬静默装 —— 那样会一声不响地失败
        silent = install_dir_writable(running_exe())
        try:
            # argv[1:] 原样带过去：开机自启时带 --autostart，重启后仍是静默启动
            launch_silent_install(installer_path, running_exe(), sys.argv[1:],
                                  silent=silent)
        except Exception as e:
            clear_pending()
            warn_box = QMessageBox(self.win if self.win.isVisible() else None)
            warn_box.setIcon(QMessageBox.Warning)
            warn_box.setWindowTitle("无法开始安装")
            warn_box.setText("启动安装程序失败")
            warn_box.setInformativeText("错误信息：%s\n\n安装包已保存到：\n%s"
                                        % (e, installer_path))
            # 不用标准按钮：Qt 默认按钮写的是英文 OK，正式对外要统一成中文
            warn_box.addButton("确定", QMessageBox.AcceptRole)
            warn_box.exec_()
            return
        if silent:
            # 静默安装从退出到新版启动之间没有任何界面，只留这一张卡片：
            # 让人知道确实在装，而不是程序崩了。卡片显示够时间后主程序才退出，
            # 之后由安装程序的进度窗口接着显示到装完。
            # 先把主窗口和更新窗口收掉，屏幕上只剩这张卡片，不然卡片浮在
            # 半个屏幕的窗口上面，看着像卡住了。
            if self._update_dlg is not None:
                self._update_dlg.close()
            self.win.hide()
            self._install_notice = InstallNotice.popup_notice()
            ulog("显示安装提示卡片，%d ms 后退出" % INSTALL_NOTICE_MS)
            QTimer.singleShot(INSTALL_NOTICE_MS, self.quit_app)
        else:
            # 需要管理员权限时会弹安装向导，用户看得见，不用额外卡片
            Toast.show_toast("请在安装向导中完成安装",
                             "当前目录需要管理员权限，无法自动安装。",
                             kind="warn", timeout=6000)
            # 留一点时间让界面刷完再退出；安装程序自己会等 3 秒
            QTimer.singleShot(300, self.quit_app)

    def _notify_update_result(self):
        """上一次更新之后第一次启动：明确告诉用户「成了」还是「没成」。

        安装是不是真的跑完了，只有新版本起来才知道 —— 所以判断放在这里，
        而不是在点「立即更新」的时候。
        """
        pending = read_pending()
        if not pending:
            cleanup_installers()
            return
        installer = str(pending.get("installer") or "")
        state = update_outcome(pending, APP_VERSION)
        clear_pending()

        if state == "done":
            cleanup_installers()
            QTimer.singleShot(400, lambda: Toast.show_toast(
                "更新完成", "已升级到 %s，设置与快捷键均已保留。" % APP_VERSION,
                kind="check", timeout=4500))
            return
        if state != "failed":
            cleanup_installers()
            return

        # 还停在旧版本：安装流程没走完（被杀软拦下、被取消、目录不可写…）
        cleanup_installers(keep=installer)
        tip = ("安装包已保存，双击即可完成升级：\n%s" % installer
               if installer else "请打开「检查更新」重新下载安装包。")
        QTimer.singleShot(400, lambda: Toast.show_toast(
            "更新未完成", tip, kind="warn", timeout=8000))

    # ------------------------------------------------------------ 设置
    def open_settings(self):
        original = config.get("hotkey")
        # 录快捷键时先停掉触发，否则按下当前组合就会当场截图
        self.hotkey.set_enabled(False)
        try:
            dlg = SettingsDialog(config, self._try_apply_hotkey, None,
                                 update_info=self._available_update,
                                 probe_hotkey=self._probe_hotkey)
            dlg.check_requested.connect(self._on_settings_check)
            # 设置页开着的时候查到新版本，箭头和「上次检查」要能当场刷新
            self._settings_dlg = dlg
            accepted = dlg.exec_() == QDialog.Accepted
            wants_update = bool(getattr(dlg, "wants_update", False))
        finally:
            self._settings_dlg = None
            self.hotkey.set_enabled(True)
        if accepted:
            self.win.set_hotkey_text(config.get("hotkey"))
            self._refresh_tray_menu()
            self.hotkey.register(config.get("hotkey"))
        else:
            # 对话框里可能已试注册新键，取消时回滚
            self.hotkey.register(original)
        if wants_update:
            # 设置已经关掉了，等这一帧结束后再开更新窗口
            QTimer.singleShot(0, self.show_update)

    def _try_apply_hotkey(self, sequence: str):
        return self.hotkey.register(normalize_sequence(sequence))

    def _probe_hotkey(self, sequence: str):
        """设置里录完组合键就调：只探测是否被占用，不改当前热键。"""
        return self.hotkey.probe_conflict(normalize_sequence(sequence))


def _install_crash_log():
    """把「程序直接消失」这类问题留证据。

    打包成 exe 后没有控制台，未捕获异常和 abort 一律无声无息 —— 用户只能
    看到窗口突然没了。这里同时接两个口子：
      - sys.excepthook：Python 层异常，连调用栈写进 crash.log
      - faulthandler：PyQt5 遇到槽函数异常会直接 abort，只有它能抓到现场
    文件放在 %APPDATA%\\我爱截图\\crash.log，跟 update.log 同一目录。
    """
    global _CRASH_FILE
    import datetime
    import traceback

    path = update_log.crash_path()
    try:
        # 反复崩溃时别把磁盘写满：超过 256KB 就换一份新的，旧的留作 .1
        if os.path.exists(path) and os.path.getsize(path) > 256 * 1024:
            os.replace(path, path + ".1")
    except Exception:
        pass
    try:
        _CRASH_FILE = open(path, "a", encoding="utf-8", buffering=1)
    except Exception:
        return

    try:
        import faulthandler
        faulthandler.enable(file=_CRASH_FILE, all_threads=True)
    except Exception:
        pass

    def _hook(exc_type, exc, tb):
        try:
            _CRASH_FILE.write("\n=== %s ===\n"
                              % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            traceback.print_exception(exc_type, exc, tb, file=_CRASH_FILE)
            _CRASH_FILE.flush()
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook


def _log_env():
    """启动时把运行环境记一行。

    换台机器排查时，「双屏且两块屏缩放不同」「150% 缩放」这类信息最关键，但
    让用户自己去系统设置里翻很麻烦，还不一定说得清。这里随启动记一次，对方
    只要把日志发过来，环境就一并有了。
    """
    try:
        import platform
        screens = []
        union = None
        try:
            primary = QApplication.primaryScreen()
            for s in QApplication.screens():
                g = s.geometry()
                union = g if union is None else union.united(g)
                screens.append("%dx%d@%.2f%s" % (
                    g.width(), g.height(), s.devicePixelRatio(),
                    "*" if s is primary else ""))
        except Exception:
            pass
        geo = "未知"
        if union is not None:
            geo = "%d,%d %dx%d" % (union.x(), union.y(), union.width(), union.height())
        update_log.log("环境：%s 版本=%s 屏=%d [%s] 虚拟桌面=%s"
                       % (platform.platform(terse=True), APP_VERSION,
                          len(screens), " ".join(screens) or "未知", geo))
    except Exception:
        pass


def main():
    _install_crash_log()
    # 必须最先做：让进程按物理像素工作。多显示器（尤其两块屏缩放比例不同）时，
    # 不声明 DPI 感知的话系统会虚拟化坐标，第二块屏抓出来是一整块黑。
    set_process_dpi_awareness()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    # 缩放比例别四舍五入：Windows 设 150% 时 Qt 默认会按 200% 画，界面比别的
    # 程序大一圈，而且抓图比例算错。PassThrough = 跟系统一致。
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("WoAiJieTu")
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    ico = QIcon(asset("app.ico"))
    app.setWindowIcon(ico)
    _log_env()

    server = acquire_single_instance()
    if server is None:
        return 0

    ctrl = AppController(app, server)
    ctrl.start(silent=autostart.AUTOSTART_ARG in sys.argv)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
