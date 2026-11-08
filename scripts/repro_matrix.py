# -*- coding: utf-8 -*-
"""2x2 矩阵：{alpha-only, colorkey} × {普通, TOOLWINDOW+NOACTIVATE}，全部顶层+TOPMOST。
每窗 PrintWindow 一张 + 最后整屏一张。"""
import ctypes
import sys
import tkinter as tk

sys.path.insert(0, r"E:\aimp-wallpaper")
from ctypes import POINTER, byref, c_ssize_t, c_void_p
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageTk
from aimp_wallpaper import desktop

user32 = desktop.user32
gdi32 = ctypes.windll.gdi32

SWP_NOMOVE, SWP_NOSIZE, SWP_NOACTIVATE = 0x2, 0x1, 0x10


class BH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class RQ(ctypes.Structure):
    _fields_ = [("b", ctypes.c_ubyte), ("g", ctypes.c_ubyte), ("r", ctypes.c_ubyte), ("a", ctypes.c_ubyte)]


class BI(ctypes.Structure):
    _fields_ = [("hdr", BH), ("pal", RQ * 2)]


def printwindow(hwnd, w, h, path):
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, 2)
    bmi = BI()
    bmi.hdr = BH(40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    px = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, px, byref(bmi), 0)
    Image.frombuffer("RGBA", (w, h), bytes(px), "raw", "BGRA", w * 4, 0).save(path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    return ok


root = tk.Tk()
root.overrideredirect(True)
root.geometry("+3000+3000")
made = []

CASES = [
    ("m1_alpha_plain", 700, 500, False, False),
    ("m2_key_plain", 700, 700, True, False),
    ("m3_alpha_tool", 1050, 500, False, True),
    ("m4_key_tool", 1050, 700, True, True),
]

for tag, x, y, key, tool in CASES:
    w = tk.Toplevel(root)
    w.overrideredirect(True)
    W, H = 300, 150
    c = tk.Canvas(w, width=W, height=H, bg=desktop.KEY_HEX if key else "#181A22",
                  highlightthickness=0, bd=0)
    c.pack()
    img = Image.new("RGB", (W, H), desktop.KEY if key else (24, 26, 34))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([1, 1, W - 2, H - 2], radius=14, fill=(24, 26, 34))
    d.rectangle([20, 60, 280, 110], fill="#FF3344")
    d.text((20, 20), tag, fill=(255, 255, 255))
    if key:
        pi = ImageTk.PhotoImage(img)
        c.create_image(0, 0, image=pi, anchor="nw")
        globals()[f"_pi_{tag}"] = pi
    w.geometry(f"+{x}+{y}")
    w.update_idletasks()
    w.update()
    hwnd = user32.GetAncestor(desktop.HWND_T(w.winfo_id()), desktop.GA_ROOT)
    ex = user32.GetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE)
    ex |= desktop.WS_EX_LAYERED
    if tool:
        ex |= desktop.WS_EX_TOOLWINDOW | desktop.WS_EX_NOACTIVATE
    user32.SetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE, ex)
    if key:
        user32.SetLayeredWindowAttributes(hwnd, 0x00030201, 255, desktop.LWA_COLORKEY | desktop.LWA_ALPHA)
    else:
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, desktop.LWA_ALPHA)
    user32.SetWindowPos(c_void_p(hwnd), c_void_p(-1), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    w.update()  # 分层化后再强制重绘
    made.append((tag, hwnd, W, H))

root.after(1800, lambda: [printwindow(h, W, H, rf"E:\aimp-wallpaper\scripts\{t}.png") for t, h, W, H in made])
root.after(2800, root.destroy)
root.mainloop()
print("done")
