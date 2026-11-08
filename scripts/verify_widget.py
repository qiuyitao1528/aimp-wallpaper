# -*- coding: utf-8 -*-
"""验证桌面层面板：在 Progman/WorkerW 子窗口里找全部 Tk 面板，抓 PrintWindow 内容。"""
import ctypes
from ctypes import POINTER, byref, c_size_t, c_ssize_t, c_void_p
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.FindWindowW.restype = c_void_p
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = c_void_p
user32.FindWindowExW.argtypes = [c_void_p, c_void_p, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [c_void_p, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [c_void_p, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [c_void_p, POINTER(wintypes.RECT)]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [c_void_p]
user32.GetWindowLongPtrW.restype = c_ssize_t
user32.GetWindowLongPtrW.argtypes = [c_void_p, ctypes.c_int]


class BH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class RQ(ctypes.Structure):
    _fields_ = [("b", ctypes.c_ubyte), ("g", ctypes.c_ubyte), ("r", ctypes.c_ubyte), ("a", ctypes.c_ubyte)]


class BI(ctypes.Structure):
    _fields_ = [("hdr", BH), ("pal", RQ * 2)]


def children_of(parent, out):
    h = None
    while True:
        h = user32.FindWindowExW(parent, h, None, None)
        if not h:
            break
        out.append(h)
    return out


targets = []
progman = user32.FindWindowW("Progman", None)
roots = []
if progman:
    roots.append(("Progman", progman))
w = c_void_p()
workers = []
h = None
while True:
    h = user32.FindWindowExW(None, h, "WorkerW", None)
    if not h:
        break
    workers.append(h)
for i, wk in enumerate(workers):
    roots.append((f"WorkerW[{i}]", wk))

for name, root in roots:
    kids = children_of(root, [])
    for kid in kids:
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(kid, cls, 128)
        if cls.value in ("Tk", "TkTopLevel"):
            txt = ctypes.create_unicode_buffer(128)
            user32.GetWindowTextW(kid, txt, 128)
            targets.append((name, kid, cls.value, txt.value))

print(f"找到 {len(targets)} 个桌面层面板：")

for idx, (name, kid, cls, txt) in enumerate(targets):
    parent = user32.FindWindowW("Progman", None)  # 仅用于展示
    pcls = ctypes.create_unicode_buffer(128)
    pp = user32.FindWindowExW(None, None, None, None)  # 占位
    r = wintypes.RECT()
    user32.GetWindowRect(kid, byref(r))
    ex = user32.GetWindowLongPtrW(kid, -20) & 0xFFFFFFFF
    W, H = r.right - r.left, r.bottom - r.top
    print(f"[{idx}] parent={name} hwnd={kid:#x} title={txt!r} rect=({r.left},{r.top}) {W}x{H} "
          f"可见={bool(user32.IsWindowVisible(kid))} LAYERED={'是' if ex & 0x80000 else '否'}")

    if W <= 0 or H <= 0:
        continue
    hdc = user32.GetWindowDC(kid)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, W, H)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(kid, mem, 2)
    bmi = BI()
    bmi.hdr = BH(40, W, -H, 1, 32, 0, 0, 0, 0, 0, 0)
    px = ctypes.create_string_buffer(W * H * 4)
    gdi32.GetDIBits(mem, bmp, 0, H, px, byref(bmi), 0)
    from PIL import Image
    Image.frombuffer("RGBA", (W, H), bytes(px), "raw", "BGRA", W * 4, 0).save(
        rf"E:\aimp-wallpaper\scripts\panel_{idx}_capture.png")
    print(f"     PrintWindow={ok} -> panel_{idx}_capture.png")
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(kid, hdc)
