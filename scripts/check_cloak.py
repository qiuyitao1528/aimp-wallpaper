# -*- coding: utf-8 -*-
"""诊断：面板窗口是否被 DWM cloak；WorkerW 层级关系。"""
import ctypes
from ctypes import POINTER, byref, c_void_p
from ctypes import wintypes

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
user32.FindWindowExW.restype = c_void_p
user32.FindWindowExW.argtypes = [c_void_p, c_void_p, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetWindowRect.argtypes = [c_void_p, POINTER(wintypes.RECT)]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [c_void_p, ctypes.c_int]

DWMWA_CLOAKED = 14


def cloak(hwnd) -> int:
    v = wintypes.DWORD()
    dwmapi.DwmGetWindowAttribute(c_void_p(hwnd), DWMWA_CLOAKED, byref(v), ctypes.sizeof(v))
    return v.value


def rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, byref(r))
    return (r.left, r.top, r.right, r.bottom)


progman = user32.FindWindowExW(None, None, "Progman", None)
print(f"Progman {progman:#x} rect={rect(progman)} cloak={cloak(progman)}")

h = None
while True:
    h = user32.FindWindowExW(None, h, "WorkerW", None)
    if not h:
        break
    print(f"WorkerW {h:#x} rect={rect(h)} cloak={cloak(h)}")
    kid = None
    kids = []
    while True:
        kid = user32.FindWindowExW(h, kid, None, None)
        if not kid:
            break
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(kid, cls, 128)
        kids.append((kid, cls.value))
    for kid, cls in kids:
        c = cloak(kid)
        print(f"   子 {kid:#x} {cls!r} rect={rect(kid)} cloak={c}({'SHELL视图' if 'SHELL' in cls else ''})")

# 我们的窗口
print("\n面板：")
for parent in [progman]:
    h = None
    while True:
        h = user32.FindWindowExW(parent, h, None, None)
        if not h:
            break
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(h, cls, 128)
        if cls.value == "TkTopLevel":
            print(f"  TkTopLevel {h:#x} parent=Progman rect={rect(h)} cloak={cloak(h)} "
                  f"可见={bool(user32.IsWindowVisible(h))}")
