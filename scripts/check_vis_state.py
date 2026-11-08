# -*- coding: utf-8 -*-
"""检查可视化窗口当前状态 + PrintWindow 抓一帧。"""
import ctypes
from ctypes import POINTER, byref, c_size_t, c_ssize_t, c_void_p
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
HWND_T = c_void_p

user32.FindWindowExW.restype = HWND_T
user32.FindWindowExW.argtypes = [HWND_T, HWND_T, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetWindowRect.argtypes = [HWND_T, POINTER(wintypes.RECT)]
user32.GetParent.restype = HWND_T
user32.GetParent.argtypes = [HWND_T]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [HWND_T]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [HWND_T, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowLongPtrW.restype = c_ssize_t
user32.GetWindowLongPtrW.argtypes = [HWND_T, ctypes.c_int]


class BH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class RQ(ctypes.Structure):
    _fields_ = [("b", ctypes.c_ubyte), ("g", ctypes.c_ubyte), ("r", ctypes.c_ubyte), ("a", ctypes.c_ubyte)]


class BI(ctypes.Structure):
    _fields_ = [("hdr", BH), ("pal", RQ * 2)]


# 枚举所有 TASEScene 看状态
h = None
while True:
    h = user32.FindWindowExW(None, h, "TASEScene", None)
    if not h:
        break
    txt = ctypes.create_unicode_buffer(128)
    user32.GetWindowTextW(h, txt, 128)
    cls = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(h, cls, 128)
    r = wintypes.RECT()
    user32.GetWindowRect(h, byref(r))
    p = user32.GetParent(h)
    pcls = ctypes.create_unicode_buffer(128)
    if p:
        user32.GetClassNameW(p, pcls, 128)
    vis = bool(user32.IsWindowVisible(h))
    print(f"{h:#x} {txt.value!r} rect=({r.left},{r.top})-({r.right},{r.bottom}) "
          f"可见={vis} parent={p and hex(p)}({pcls.value})")

vis = user32.FindWindowExW(None, None, "TASEScene", "可视化")
if not vis:
    raise SystemExit("没有可视化窗口")
r = wintypes.RECT()
user32.GetWindowRect(vis, byref(r))
w, hh = r.right - r.left, r.bottom - r.top
hdc = user32.GetWindowDC(vis)
mem = gdi32.CreateCompatibleDC(hdc)
bmp = gdi32.CreateCompatibleBitmap(hdc, w, hh)
gdi32.SelectObject(mem, bmp)
ok = user32.PrintWindow(vis, mem, 2)
bmi = BI()
bmi.hdr = BH(40, w, -hh, 1, 32, 0, 0, 0, 0, 0, 0)
px = ctypes.create_string_buffer(w * hh * 4)
gdi32.GetDIBits(mem, bmp, 0, hh, px, byref(bmi), 0)
from PIL import Image
Image.frombuffer("RGBA", (w, hh), bytes(px), "raw", "BGRA", w * 4, 0).save(
    r"E:\aimp-wallpaper\scripts\vis_printwindow.png")
print(f"PrintWindow={ok} -> vis_printwindow.png")
gdi32.DeleteObject(bmp)
gdi32.DeleteDC(mem)
user32.ReleaseDC(vis, hdc)
