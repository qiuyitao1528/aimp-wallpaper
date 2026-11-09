# -*- coding: utf-8 -*-
"""测量：SetWallpaper 调用耗时 + 调用后多久屏幕才真正变成新图。"""
import os
import sys
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import comtypes
from PIL import Image, ImageGrab

from aimp_wallpaper import wallpaper

comtypes.CoInitialize()
OUT = os.path.join(os.environ["LOCALAPPDATA"], "aimp-wallpaper", "_lat")
os.makedirs(OUT, exist_ok=True)
SX, SY = 500, 300
W, H = 1920, 1080
dw = wallpaper._get_wallpaper_com()
mid = dw.GetMonitorDevicePathAt(0)


def sample():
    return ImageGrab.grab(bbox=(SX, SY, SX + 1, SY + 1)).convert("RGB").getpixel((0, 0))


def run(second_color, name):
    red = os.path.join(OUT, "r.png")
    Image.new("RGB", (W, H), (200, 30, 30)).save(red, "PNG")
    dw.SetWallpaper(mid, red)
    dw.SetPosition(wallpaper.DWPOS_FILL)
    time.sleep(1.5)
    p2 = os.path.join(OUT, name)
    Image.new("RGB", (W, H), second_color).save(p2, "PNG")
    t0 = time.perf_counter()
    dw.SetWallpaper(mid, p2)
    dw.SetPosition(wallpaper.DWPOS_FILL)
    t_call = (time.perf_counter() - t0) * 1000
    t_visible = None
    while time.perf_counter() - t0 < 2.0:
        c = sample()
        if abs(c[0] - second_color[0]) < 20:
            t_visible = (time.perf_counter() - t0) * 1000
            break
        time.sleep(0.008)
    print(f"{name}: 调用耗时={t_call:.0f}ms | 上屏延迟={t_visible:.0f}ms" if t_visible
          else f"{name}: 调用耗时={t_call:.0f}ms | 2s 内未上屏")


run((30, 30, 200), "b1.png")
run((30, 200, 30), "b2.png")
run((200, 200, 30), "b3.png")
for f in os.listdir(OUT):
    try:
        os.remove(os.path.join(OUT, f))
    except OSError:
        pass
os.rmdir(OUT)
