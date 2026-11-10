# -*- coding: utf-8 -*-
"""端到端验证开机启动：真实 exe + 真实注册表 + 配置开关。"""
import ctypes
import json
import os
import subprocess
import time
import winreg

EXE = os.path.expandvars(r"%LOCALAPPDATA%\Programs\我爱截图\我爱截图.exe")
CFG = os.path.expandvars(r"%APPDATA%\我爱截图\config.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "WoAiJieTu"

u32 = ctypes.WinDLL("user32", use_last_error=True)
results = []
pids = []


def check(label, cond):
    print(("PASS  " if cond else "FAIL  ") + label)
    results.append(bool(cond))


def kill():
    subprocess.run(["taskkill", "/F", "/IM", "我爱截图.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)


def refresh_pids():
    del pids[:]
    pids.extend(pid_of())


def visible_windows():
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        pid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and u32.IsWindowVisible(hwnd):
            n = u32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u32.GetWindowTextW(hwnd, buf, n + 1)
                out.append(buf.value)
        return True

    u32.EnumWindows(cb, 0)
    return out


def pid_of():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-Process -Name 我爱截图 -ErrorAction SilentlyContinue).Id"],
                       capture_output=True, text=True)
    return [int(x) for x in r.stdout.split() if x.strip().isdigit()]


def reg_value():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            v, _ = winreg.QueryValueEx(k, VALUE)
            return str(v)
    except OSError:
        return ""


def write_reg(cmd):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        winreg.SetValueEx(k, VALUE, 0, winreg.REG_SZ, cmd)


def drop_reg():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, VALUE)
    except OSError:
        pass


def load_cfg():
    with open(CFG, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cfg(data):
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def launch(*args):
    subprocess.Popen([EXE] + list(args), close_fds=True)
    time.sleep(4.5)
    refresh_pids()


orig = load_cfg()
try:
    kill()

    # --- 1. 开关为开 + 旧路径条目：启动后应刷新为当前 exe ---
    cfg = load_cfg()
    cfg["auto_start"] = True
    save_cfg(cfg)
    write_reg(r'"C:\old\dir\我爱截图.exe" --autostart')   # 模拟换目录/重装后的旧条目
    launch()
    wins = visible_windows()
    cmd = reg_value()
    check("正常启动后有主界面窗口", any("我爱截图" in w for w in wins))
    check("注册表已写入启动项", bool(cmd))
    check("启动命令指向已安装的 exe", EXE.lower() in cmd.lower())
    check("启动命令带 --autostart", "--autostart" in cmd)
    print("   命令:", cmd)
    kill()

    # --- 2. 带 --autostart 启动：应静默进托盘，不弹窗 ---
    subprocess.Popen([EXE, "--autostart"], close_fds=True)
    time.sleep(5)
    refresh_pids()
    check("静默启动后进程仍在运行", bool(pids))
    wins = visible_windows()
    check("静默启动不显示主界面", not wins)
    if wins:
        print("   意外窗口:", wins)
    kill()

    # --- 3. 关掉开关：启动后注册表应被清理 ---
    cfg = load_cfg()
    cfg["auto_start"] = False
    save_cfg(cfg)
    launch()
    check("关闭开关后启动项被删除", reg_value() == "")
    kill()

    # --- 4. 外部删掉启动项后，开关应自动回落为关，且不再加回来 ---
    cfg = load_cfg()
    cfg["auto_start"] = True
    save_cfg(cfg)
    write_reg('"%s" --autostart' % EXE)
    launch()
    drop_reg()          # 模拟任务管理器里禁用
    kill()
    launch()
    check("外部删除启动项后配置自动变为关", load_cfg().get("auto_start") is False)
    check("不会把用户删掉的启动项又加回来", reg_value() == "")
    kill()
finally:
    kill()
    save_cfg(orig)
    drop_reg()
    print("\ncleanup done, config restored, autostart entry cleared")
    print("%d/%d passed" % (sum(1 for r in results if r), len(results)))
