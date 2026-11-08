# -*- coding: utf-8 -*-
"""三对照实验：C=裸窗口 / D=只分层 / E=只钉层，各 PrintWindow。"""
import ctypes
import sys
import tkinter as tk

sys.path.insert(0, r"E:\aimp-wallpaper")
from ctypes import POINTER, byref
from ctypes import wintypes

from PIL import Image, ImageDraw
from aimp_wallpaper import desktop

user32 = desktop.user32
gdi32 = ctypes.windll.gdi32


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
    print(f"{path} PrintWindow={ok}")


root = tk.Tk()
root.overrideredirect(True)
root.geometry("+3000+3000")
results = {}


def make(tag, x, y, layered: bool, pin: bool):
    w = tk.Toplevel(root)
    w.overrideredirect(True)
    W, H = 300, 120
    c = tk.Canvas(w, width=W, height=H, bg="#181A22", highlightthickness=0, bd=0)
    c.pack()
    c.create_rectangle(20, 40, 280, 80, fill="#FF3344", outline="")
    c.create_text(30, 20, text=f"{tag}", fill="#FFFFFF", anchor="w")
    w.geometry(f"+{x}+{y}")
    w.update_idletasks()
    w.update()
    hwnd = user32.GetAncestor(desktop.HWND_T(w.winfo_id()), desktop.GA_ROOT)
    if layered:
        ex = user32.GetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE, ex | desktop.WS_EX_LAYERED)
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, desktop.LWA_ALPHA)
        w.update()
    if pin:
        desktop.pin_to_desktop(hwnd, x, y, W, H)
        w.update()
    results[tag] = (hwnd, W, H)
    return w


make("C", 700, 400, False, False)
make("D", 700, 550, True, False)
make("E", 700, 700, False, True)
root.after(1500, lambda: [printwindow(*results[k], rf"E:\aimp-wallpaper\scripts\cde_{k}.png") for k in results])
root.after(2500, root.destroy)
root.mainloop()
print("done")
