# -*- coding: utf-8 -*-
"""全新机器首启验证：隔离 LOCALAPPDATA 到空目录（等价别人新装），
验证 config/日志/壁纸产物/覆盖窗口/托盘 是否全部就绪。"""
import ctypes
import glob
import json
import os
import shutil
import subprocess
import tempfile
import time
from ctypes import wintypes

SRC = r"E:\aimp-wallpaper\dist-setup\aimp-wallpaper"
TMP = os.path.join(tempfile.gettempdir(), "aimp-fresh2")
APP = os.path.join(TMP, "app")
LA = os.path.join(TMP, "localappdata")
for d in (APP, LA):
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
shutil.copytree(SRC, APP, dirs_exist_ok=True)
if os.path.exists(os.path.join(APP, "portable.flag")):
    os.remove(os.path.join(APP, "portable.flag"))  # 走安装版配置路径（%LOCALAPPDATA%）
for stale in glob.glob(os.path.join(APP, "config.json")):
    os.remove(stale)

env = dict(os.environ)
env["LOCALAPPDATA"] = LA
exe = os.path.join(APP, "aimp-wallpaper.exe")
proc = subprocess.Popen([exe], cwd=APP, env=env)
print("启动 PID:", proc.pid)
time.sleep(18)

cfg_path = os.path.join(LA, "aimp-wallpaper", "config.json")
log_path = os.path.join(LA, "aimp-wallpaper", "aimp-wallpaper.log")
out_dir = os.path.join(LA, "aimp-wallpaper")
ok = True

print("--- config ---")
if os.path.exists(cfg_path):
    c = json.load(open(cfg_path, encoding="utf-8"))
    print("  OK 建好，键数:", len(c), "| 记录原壁纸:", bool(c.get("original_wallpaper")))
else:
    print("  FAIL 未创建")
    ok = False

print("--- 日志 ---")
if os.path.exists(log_path):
    txt = open(log_path, encoding="utf-8", errors="replace").read()
    lines = [ln for ln in txt.splitlines() if any(
        k in ln for k in ("启动", "已更新", "失败", "渲染路径", "异常", "Error"))]
    print("  OK，关键行:")
    for ln in lines[:8]:
        print("   ", ln[:130])
    if "已更新" not in txt:
        print("  FAIL 没有成功渲染记录")
        ok = False
else:
    print("  FAIL 未创建")
    ok = False

print("--- 壁纸产物 ---")
pngs = glob.glob(os.path.join(out_dir, "wallpaper_*.png"))
print("  OK", [os.path.basename(p) for p in pngs] if pngs else "FAIL 未生成")
if not pngs:
    ok = False

print("--- 覆盖窗口 ---")
user32 = ctypes.WinDLL("user32")
found = []


@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(hwnd, lp):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == proc.pid:
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value == "TkTopLevel":
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append({"visible": bool(user32.IsWindowVisible(hwnd)),
                          "size": (r.right - r.left, r.bottom - r.top),
                          "pos": (r.left, r.top)})
    return True


user32.EnumWindows(cb, 0)
for f in found:
    print("  ", f)
if not any(f["visible"] and f["size"][0] > 100 for f in found):
    print("  FAIL 没有可见频谱面板")
    ok = False

alive = proc.poll() is None
print("--- 进程存活:", alive, "---")
if not alive:
    print("  FAIL 进程已退出")
    ok = False

proc.kill()
time.sleep(1)
print("=== 结论:", "全新环境首启全部通过" if ok else "存在问题，需修", "===")
