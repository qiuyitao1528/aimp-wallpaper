# -*- coding: utf-8 -*-
"""枚举 AIMP 进程的全部顶层窗口和子窗口，找可视化窗口。"""
import ctypes
from ctypes import POINTER, byref, c_void_p
from ctypes import wintypes

user32 = ctypes.windll.user32

ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, c_void_p, wintypes.LPARAM)
user32.EnumWindows.argtypes = [ENUMPROC, wintypes.LPARAM]
user32.EnumChildWindows.argtypes = [c_void_p, ENUMPROC, wintypes.LPARAM]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [c_void_p, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [c_void_p, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [c_void_p, POINTER(wintypes.DWORD)]
user32.GetWindowRect.argtypes = [c_void_p, POINTER(wintypes.RECT)]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [c_void_p]


def info(hwnd):
    cls = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(hwnd, cls, 128)
    txt = ctypes.create_unicode_buffer(128)
    user32.GetWindowTextW(hwnd, txt, 128)
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, byref(r))
    vis = bool(user32.IsWindowVisible(hwnd))
    return cls.value, txt.value, (r.right - r.left, r.bottom - r.top), vis


def dump_tree(hwnd, depth, lines):
    cls, txt, size, vis = info(hwnd)
    pad = "  " * depth
    lines.append(f"{pad}{hwnd:#x} {cls!r} {txt[:30]!r} {size[0]}x{size[1]} {'可见' if vis else '隐藏'}")
    if depth >= 4:
        return
    user32.EnumChildWindows(c_void_p(hwnd), ENUMPROC(lambda c, _l: (dump_tree(c, depth + 1, lines), True)[1], ), 0)


def cb(hwnd, _lp):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, byref(pid))
    if pid.value == TARGET_PID:
        cls, txt, size, vis = info(hwnd)
        if not cls.startswith(("MSCTIME", "tooltips", "#32768", "Windows.UI")):
            lines.append(f"TOP {hwnd:#x} {cls!r} {txt[:30]!r} {size[0]}x{size[1]} {'可见' if vis else '隐藏'}")
            dump_tree(hwnd, 1, lines)
    return True


import subprocess
out = subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command",
     "Get-Process AIMP -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
    capture_output=True, text=True).stdout.strip()
pids = [int(x) for x in out.split() if x.strip().isdigit()]
print("AIMP PIDs:", pids)
if not pids:
    raise SystemExit(1)
TARGET_PID = pids[0]

lines = []
user32.EnumWindows(ENUMPROC(cb), 0)
print("\n".join(lines))
