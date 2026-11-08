# -*- coding: utf-8 -*-
"""A/B 实验 v2：进程内 PrintWindow 抓取（alpha-only vs colorkey）。"""
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
    im = Image.frombuffer("RGBA", (w, h), bytes(px), "raw", "BGRA", w * 4, 0)
    im.save(path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    print(f"PrintWindow={ok} -> {path}")


root = tk.Tk()
root.overrideredirect(True)
root.geometry("+2000+2000")  # 移出可视区


def make(x, y, colorkey: bool):
    w = tk.Toplevel(root)
    w.overrideredirect(True)
    W, H = 300, 120
    c = tk.Canvas(w, width=W, height=H, bg=desktop.KEY_HEX if colorkey else "#181A22",
                  highlightthickness=0, bd=0)
    c.pack()
    if colorkey:
        img = Image.new("RGB", (W, H), desktop.KEY)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([1, 1, W - 2, H - 2], radius=14, fill=(24, 26, 34))
        d.text((30, 50), "B colorkey", fill=(242, 244, 248))
        pi = ImageTk.PhotoImage(img)
        c.create_image(0, 0, image=pi, anchor="nw")
        globals()[f"_pi{colorkey}"] = pi
    c.create_rectangle(20, 80, 60, 100, fill="#FF3344", outline="")
    c.create_text(100, 90, text="A alpha-only" if not colorkey else "B colorkey",
                  fill="#FFFFFF", anchor="w")
    w.geometry(f"+{x}+{y}")
    w.update_idletasks()
    w.update()
    hwnd = user32.GetAncestor(desktop.HWND_T(w.winfo_id()), desktop.GA_ROOT)
    if colorkey:
        desktop.style_desktop_widget(hwnd, 255)
        desktop.pin_to_desktop(hwnd, x, y, W, H)
    else:
        ex = user32.GetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, desktop.GWL_EXSTYLE,
                                 ex | desktop.WS_EX_LAYERED | desktop.WS_EX_TOOLWINDOW)
        user32.SetLayeredWindowAttributes(hwnd, 0, 255, desktop.LWA_ALPHA)
        desktop.pin_to_desktop(hwnd, x, y, W, H)
    # 关键：分层化会重置窗口表面，必须再强制重绘一次
    w.update_idletasks()
    w.update()
    return hwnd, W, H


ha = make(700, 700, False)
hb = make(700, 850, True)
root.after(1500, lambda: printwindow(ha[0], 300, 120, r"E:\aimp-wallpaper\scripts\ab_alpha.png"))
root.after(2500, lambda: printwindow(hb[0], 300, 120, r"E:\aimp-wallpaper\scripts\ab_key.png"))
root.after(3500, root.destroy)
root.mainloop()
print("done")
