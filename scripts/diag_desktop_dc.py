# -*- coding: utf-8 -*-
"""诊断：换壁纸后，从哪个窗口的 DC 能读到新壁纸像素。"""
import ctypes
import os
import sys
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import comtypes
from ctypes import wintypes
from PIL import Image

from aimp_wallpaper import desktop, wallpaper

desktop.gdi32.GetPixel.restype = wintypes.DWORD
desktop.gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]

OUT = os.path.join(os.environ["LOCALAPPDATA"], "aimp-wallpaper", "_diag")
os.makedirs(OUT, exist_ok=True)
W, H = 1920, 1080
blue = os.path.join(OUT, "blue.png")
Image.new("RGB", (W, H), (30, 30, 200)).save(blue, "PNG")

comtypes.CoInitialize()
dw = wallpaper._get_wallpaper_com()
mid = dw.GetMonitorDevicePathAt(0)
dw.SetWallpaper(mid, blue)
dw.SetPosition(wallpaper.DWPOS_FILL)
time.sleep(1.5)


def px(hwnd, x=600, y=400):
    hdc = desktop.user32.GetDC(hwnd)
    if not hdc:
        return "无DC"
    try:
        c = desktop.gdi32.GetPixel(hdc, x, y)
        if c == 0xFFFFFFFF:
            return "失败"
        return (c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF)
    finally:
        desktop.user32.ReleaseDC(hwnd, hdc)


progman = desktop.user32.FindWindowW("Progman", None)
parent = desktop.find_desktop_parent()
print("Progman:", hex(progman) if progman else None, "-> 像素:", px(progman))
print("desktop_parent:", hex(parent) if parent else None, "-> 像素:", px(parent))

defview = desktop.user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
print("SHELLDLL_DefView:", hex(defview) if defview else None, "-> 像素:", px(defview))
par = desktop.user32.GetParent(defview) if defview else None
print("DefView 的父窗:", hex(par) if par else None, "-> 像素:", px(par) if par else "-")

# 期望值
print("期望新壁纸颜色: (30, 30, 200)")
os.remove(blue)
try:
    os.rmdir(OUT)
except OSError:
    pass
