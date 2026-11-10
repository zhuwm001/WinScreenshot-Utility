# -*- coding: utf-8 -*-
"""我爱截图 —— 程序入口与总控。"""
import os
import sys

from PyQt5.QtCore import QObject, QRect, Qt, QTimer
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QSystemTrayIcon

import theme
import autostart
from app_config import APP_NAME, APP_VERSION, config
from hotkey import HotkeyManager, normalize_sequence
from main_window import MainWindow
from overlay import CaptureOverlay
from paths import asset
from pin_window import PinWindow
from screenshot import grab_virtual_desktop, patch_region
from settings_dialog import SettingsDialog
from toast import Toast

SERVER_NAME = "WoAiJieTu.SingleInstance.v1"


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
        self.tray.setToolTip(APP_NAME)
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
        shot, vgeo = grab_virtual_desktop()

        self._restore_main = self.win.isVisible()
        self._hide_rect = QRect()
        if config.get("hide_self") and self.win.isVisible():
            # 自己的窗口要先藏起来，否则会被截进去；但画面已经拍好，
            # 只需要等它真正消失后把那一小块区域重抓一次补回去。
            self._hide_rect = QRect(self.win.frameGeometry())
            self.win.hide()
            # 等窗口真正从合成器上撤走（约两帧），再只补抓这一块
            QTimer.singleShot(120, lambda: self._open_overlay(shot, vgeo))
        else:
            QTimer.singleShot(0, lambda: self._open_overlay(shot, vgeo))

    def _release_guard(self):
        self._capture_guard = False

    def _open_overlay(self, shot=None, vgeo=None):
        if shot is not None and not shot.isNull() and not self._hide_rect.isNull():
            patch_region(shot, vgeo, self._hide_rect)
        self._hide_rect = QRect()

        self.overlay = CaptureOverlay(config.get("pen_color"),
                                     config.get("text_size"),
                                     config.get("text_bold"),
                                     shot=shot, vgeo=vgeo)
        self.overlay.finished.connect(self._on_capture_done)
        self.overlay.cancelled.connect(self._on_capture_cancelled)
        self.overlay.pinned.connect(self._on_pinned)
        self.overlay.destroyed.connect(self._on_overlay_destroyed)
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
        pin = PinWindow(image, screen_pos, self._screen_dpr())
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

    def _restore_main_window(self):
        # 恢复主界面但不抢焦点，方便用户直接粘贴到其他窗口
        if self._restore_main and not self.win.isVisible():
            self.win.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.win.show()
        self._restore_main = False

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
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

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
