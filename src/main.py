# -*- coding: utf-8 -*-
"""我爱截图 —— 程序入口与总控。"""
import os
import sys
import time

from PyQt5.QtCore import QObject, QRect, Qt, QTimer
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QSystemTrayIcon

import theme
import autostart
from app_config import APP_NAME, APP_VERSION, config
from hotkey import HotkeyManager, normalize_sequence
from main_window import MainWindow
from overlay import CaptureSession
from paths import asset
from pin_window import PinWindow
from screenshot import capture_desktop, set_process_dpi_awareness
from settings_dialog import SettingsDialog
from toast import Toast
from update import (UpdateChecker, launch_silent_install, running_exe)
from update_dialog import MODE_ERROR, MODE_LATEST, MODE_NEW, UpdateDialog

SERVER_NAME = "WoAiJieTu.SingleInstance.v1"

# 启动后多久去问 GitHub（留出时间给界面先起来）
UPDATE_DELAY_MS = 6000
# 常驻期间两次自动检查之间至少隔多久（启动那一次不受这个限制）
UPDATE_INTERVAL = 6 * 3600
# 运行期间多久看一眼「该不该查了」。托盘程序可能几天不退出，只在启动时查
# 就永远等不到新版本；这里每小时醒一次，真正请求仍受 UPDATE_INTERVAL 限制。
UPDATE_POLL_MS = 60 * 60 * 1000


def update_due(last_ts, now=None, interval=UPDATE_INTERVAL) -> bool:
    """常驻期间是否到了该自动检查的时候。

    只用于定时器那一路；启动那一次走 _startup_update_check，不受这里限制。
    """
    try:
        last_ts = int(last_ts or 0)
    except (TypeError, ValueError):
        last_ts = 0
    if last_ts <= 0:
        return True
    return (now if now is not None else time.time()) - last_ts >= interval


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
        self._hide_rect = QRect()
        self._checker = None
        self._update_dlg = None
        # 常驻托盘时也要持续发现新版本，不能只靠「下次启动」
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(UPDATE_POLL_MS)
        self._update_timer.timeout.connect(self._schedule_update_check)

        self.win = MainWindow(config.get("hotkey"))
        self.win.capture_requested.connect(self.start_capture)
        self.win.settings_requested.connect(self.open_settings)
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

    def _sync_autostart(self):
        """校正注册表里的启动项，与设置里的开关保持一致。"""
        on = bool(config.get("auto_start"))
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
        act_update.triggered.connect(lambda: self.check_updates(silent=False))

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
        self.show_main()

    # ------------------------------------------------------------ 窗口
    def show_main(self):
        if not self.win.isVisible():
            self.win.center_on_screen()
        self.win.show_and_raise()

    def hide_to_tray(self):
        self.win.hide()
        if not getattr(self, "_tray_tip_shown", False):
            self._tray_tip_shown = True
            Toast.show_toast("已隐藏到托盘", "程序在桌面右下角继续运行，双击托盘图标可重新打开。",
                             kind="info", timeout=3000)

    def on_main_close(self):
        if config.get("close_action") == "exit":
            self.quit_app()
        else:
            self.hide_to_tray()

    def quit_app(self):
        try:
            self.hotkey.close()
        except Exception:
            pass
        self.tray.hide()
        self.win.hide()
        QApplication.quit()

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

    def _open_overlay(self, desk=None):
        if desk is not None and not self._hide_rect.isNull():
            desk.patch(self._hide_rect)
        self._hide_rect = QRect()

        self.overlay = CaptureSession(desk,
                                      config.get("pen_color"),
                                      config.get("text_size"),
                                      config.get("text_bold"))
        self.overlay.finished.connect(self._on_capture_done)
        self.overlay.cancelled.connect(self._on_capture_cancelled)
        self.overlay.pinned.connect(self._on_pinned)
        self.overlay.closed.connect(self._on_overlay_destroyed)
        self.overlay.show_overlay()

    def _on_overlay_destroyed(self, *_):
        self.overlay = None

    def _on_capture_done(self, image):
        self._persist_text_style()
        self.overlay = None
        self._restore_main_window()
        Toast.show_toast("已复制到剪贴板", "可直接到其他窗口按 Ctrl+V 粘贴。",
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
        """启动后在后台问一次，**不看** 6 小时节流。

        节流时间戳在每次检查时都会刷新（包括用户手动点的那次），如果启动也
        看它，就会出现「刚手动查过 -> 重启 -> 明明有新版本却不提示」。
        启动是低频事件，多问一次的成本可以忽略。
        """
        if not config.get("check_update"):
            return
        QTimer.singleShot(UPDATE_DELAY_MS, lambda: self.check_updates(silent=True))

    def _schedule_update_check(self):
        """常驻期间按频率问一次 GitHub；关掉「自动检查」就完全不问。"""
        if not config.get("check_update"):
            return
        if not update_due(config.get("update_last_check")):
            return
        QTimer.singleShot(UPDATE_DELAY_MS, lambda: self.check_updates(silent=True))

    def check_updates(self, silent: bool = False):
        if self._checker is not None or self._update_dlg is not None:
            return
        # 先记时间：失败了也别每次开机都重试，6 小时后再来
        config.set("update_last_check", int(time.time()))
        config.save()
        self._checker = UpdateChecker(self)
        self._checker.found.connect(self._on_update_found)
        self._checker.latest.connect(lambda ver: self._on_update_latest(ver, silent))
        self._checker.failed.connect(lambda msg: self._on_update_failed(msg, silent))
        self._checker.check(APP_VERSION)
        if not silent:
            Toast.show_toast("正在检查更新", "正在连接 GitHub…", kind="info", timeout=2000)

    def _drop_checker(self):
        checker = self._checker
        self._checker = None
        if checker is not None:
            checker.deleteLater()

    def _on_update_found(self, info):
        self._drop_checker()
        self._open_update_dialog(info, MODE_NEW)

    def _on_update_latest(self, version, silent):
        self._drop_checker()
        if not silent:
            self._open_update_dialog(None, MODE_LATEST)

    def _on_update_failed(self, message, silent):
        self._drop_checker()
        if not silent:
            self._open_update_dialog(None, MODE_ERROR, message)

    def _open_update_dialog(self, info, mode, message: str = ""):
        if self._update_dlg is not None:
            self._update_dlg.raise_()
            self._update_dlg.activateWindow()
            return
        parent = self.win if self.win.isVisible() else None
        dlg = UpdateDialog(info=info, message=message, mode=mode, parent=parent)
        dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dlg.ready_to_install.connect(self._install_update)
        dlg.retry_requested.connect(self._retry_check)
        dlg.finished.connect(self._on_update_dialog_closed)
        self._update_dlg = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_update_dialog_closed(self, *_):
        self._update_dlg = None

    def _retry_check(self):
        QTimer.singleShot(200, lambda: self.check_updates(silent=False))

    def _install_update(self, installer_path: str):
        try:
            # argv[1:] 原样带过去：开机自启时带 --autostart，重启后仍是静默启动
            launch_silent_install(installer_path, running_exe(), sys.argv[1:])
        except Exception as e:
            QMessageBox.warning(
                self.win if self.win.isVisible() else None, "无法开始安装",
                "启动安装程序失败：%s\n\n安装包已下载到：\n%s" % (e, installer_path))
            return
        Toast.show_toast("正在安装新版本", "软件会自动关闭并重新打开。",
                         kind="check", timeout=2500)
        # 留一点时间让界面刷完再退出；安装程序自己会等 3 秒
        QTimer.singleShot(300, self.quit_app)

    # ------------------------------------------------------------ 设置
    def open_settings(self):
        original = config.get("hotkey")
        # 录快捷键时先停掉触发，否则按下当前组合就会当场截图
        self.hotkey.set_enabled(False)
        try:
            dlg = SettingsDialog(config, self._try_apply_hotkey, None)
            accepted = dlg.exec_() == QDialog.Accepted
        finally:
            self.hotkey.set_enabled(True)
        if accepted:
            self.win.set_hotkey_text(config.get("hotkey"))
            self._refresh_tray_menu()
            self.hotkey.register(config.get("hotkey"))
        else:
            # 对话框里可能已试注册新键，取消时回滚
            self.hotkey.register(original)

    def _try_apply_hotkey(self, sequence: str):
        return self.hotkey.register(normalize_sequence(sequence))


def main():
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

    server = acquire_single_instance()
    if server is None:
        return 0

    ctrl = AppController(app, server)
    ctrl.start(silent=autostart.AUTOSTART_ARG in sys.argv)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
