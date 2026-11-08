# -*- coding: utf-8 -*-
"""枚举当前用户桌面所有顶层窗口，找 Tk 类（小部件）窗口及所在进程。"""
import ctypes
from ctypes import POINTER, byref, c_ssize_t, c_void_p
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.FindWindowW.restype = c_void_p
user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [c_void_p, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [c_void_p, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [c_void_p, POINTER(wintypes.DWORD)]
user32.GetParent.restype = c_void_p
user32.GetParent.argtypes = [c_void_p]
user32.IsWindowVisible.argtypes = [c_void_p]
user32.IsWindowVisible.restype = wintypes.BOOL

ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, c_void_p, wintypes.LPARAM)
user32.EnumWindows.argtypes = [ENUMPROC, wintypes.LPARAM]

rows = []


def cb(hwnd, _lp):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, byref(pid))
    cls = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(hwnd, cls, 128)
    txt = ctypes.create_unicode_buffer(128)
    user32.GetWindowTextW(hwnd, txt, 128)
    if cls.value in ("Tk", "TkTopLevel", "") or "aimp" in txt.value.lower():
        pcls = ""
        p = user32.GetParent(hwnd)
        if p:
            pc = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(p, pc, 128)
            pcls = pc.value
        rows.append((hwnd, pid.value, cls.value, txt.value,
                     bool(user32.IsWindowVisible(hwnd)), pcls))
    return True


user32.EnumWindows(ENUMPROC(cb), 0)
# 列出 python 相关进程名
import subprocess
out = subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"],
    capture_output=True, text=True).stdout
py_pids = []
for line in out.splitlines():
    if "aimp_wallpaper" in line:
        py_pids.append(int(line.split("|")[0]))

print("python(aimp_wallpaper) PIDs:", py_pids)
print(f"{'hwnd':>10} {'pid':>7} {'类名':<12} {'标题':<20} 可见  父类名")
for hwnd, pid, cls, txt, vis, pcls in rows:
    mark = "  <== 本应用" if pid in py_pids else ""
    print(f"{hwnd:#010x} {pid:>7} {cls:<12} {txt[:20]:<20} {vis}   {pcls}{mark}")
