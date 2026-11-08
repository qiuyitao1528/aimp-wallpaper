# -*- coding: utf-8 -*-
"""F 实验：SetParent 到桌面层 + UpdateLayeredWindow 自绘内容，验证能否显示。"""
import ctypes
import sys
import tkinter as tk

sys.path.insert(0, r"E:\aimp-wallpaper")
from ctypes import POINTER, byref, c_void_p, sizeof, sizeof
from ctypes import wintypes

from PIL import Image, ImageDraw
from aimp_wallpaper import desktop

user32 = desktop.user32
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.windll.gdi32

WS_EX_LAYERED = 0x80000
ULW_ALPHA = 2
ULW_OPAQUE = 4
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 1)]


user32.UpdateLayeredWindow.argtypes = [c_void_p, c_void_p, POINTER(POINT), POINTER(SIZE),
                                       c_void_p, POINTER(POINT), wintypes.COLORREF,
                                       POINTER(BLENDFUNCTION), wintypes.DWORD]

W, H = 300, 120


def ulw_draw(hwnd, img: Image.Image, x, y):
    """把 RGBA 图更新到分层窗口（位置用 SetWindowPos，ULW 只传像素）。"""
    w, h = img.size
    buf = bytearray(img.tobytes())
    for i in range(0, len(buf), 4):
        a = buf[i + 3]
        buf[i] = buf[i] * a // 255
        buf[i + 1] = buf[i + 1] * a // 255
        buf[i + 2] = buf[i + 2] * a // 255

    bmi = BITMAPINFO()
    bmi.bmiHeader = BITMAPINFOHEADER(sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bits = c_void_p()
    bmp = gdi32.CreateDIBSection(screen_dc, byref(bmi), 0, byref(bits), None, 0)
    if not bmp or not bits.value:
        print(f"CreateDIBSection 失败 bmp={bmp} bits={bits.value} err={ctypes.get_last_error()}")
        return False
    gdi32.SelectObject(mem_dc, bmp)
    ctypes.memmove(bits, bytes(buf), len(buf))
    blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
    user32.SetWindowPos(hwnd, None, x, y, w, h, 0x4 | 0x10 | 0x2)  # NOZORDER|NOACTIVATE|NOREDRAW? 用基本位
    ok = user32.UpdateLayeredWindow(hwnd, None, None, None,
                                    mem_dc, byref(POINT(0, 0)), 0, byref(blend), ULW_ALPHA)
    if not ok:
        print(f"ULW 失败 err={ctypes.get_last_error()}")
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(None, screen_dc)
    return ok


root = tk.Tk()
root.overrideredirect(True)
root.geometry("+3000+3000")

w = tk.Toplevel(root)
w.overrideredirect(True)
c = tk.Canvas(w, width=W, height=H, highlightthickness=0, bd=0)
c.pack()
c.create_text(5, 5, text="ULW test", fill="#FF0000", anchor="nw")
w.geometry(f"+700+700")
w.update_idletasks()
w.update()
hwnd = user32.GetAncestor(desktop.HWND_T(w.winfo_id()), desktop.GA_ROOT)
ex = user32.GetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE)
user32.SetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE, ex | WS_EX_LAYERED | desktop.WS_EX_TOOLWINDOW | desktop.WS_EX_NOACTIVATE)
# 钉到桌面层
parent = desktop.find_desktop_parent()
user32.SetParent(desktop.HWND_T(hwnd), parent)
pr = wintypes.RECT()
user32.GetWindowRect(parent, byref(pr))
print(f"parent={parent:#x} parentrect={pr.left},{pr.top}")

img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([1, 1, W - 2, H - 2], radius=14, fill=(24, 26, 34, 235))
d.rounded_rectangle([1, 1, W - 2, H - 2], radius=14, outline=(90, 96, 120, 255), width=1)
d.rectangle([20, 40, 280, 80], fill=(255, 51, 68, 255))
d.text((30, 15), "F: ULW pinned", fill=(255, 255, 255, 255))

ok = ulw_draw(hwnd, img, 700 - pr.left, 700 - pr.top)
print(f"ULW ok={ok}")

root.after(3000, root.destroy)
root.mainloop()
print("done")
