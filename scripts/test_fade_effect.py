# -*- coding: utf-8 -*-
"""验证自绘淡入：桌面先红，再用 fade 淡入蓝色，采样看是否有中间色帧。"""
import os
import sys
import threading
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import comtypes
from PIL import Image, ImageGrab

from aimp_wallpaper import desktop, fade, wallpaper

comtypes.CoInitialize()
OUT = os.path.join(os.environ["LOCALAPPDATA"], "aimp-wallpaper", "_fadetest")
os.makedirs(OUT, exist_ok=True)
SX, SY = 500, 300
W, H = 1920, 1080

red = os.path.join(OUT, "red.png")
Image.new("RGB", (W, H), (200, 30, 30)).save(red, "PNG")
dw = wallpaper._get_wallpaper_com()
mid = dw.GetMonitorDevicePathAt(0)
dw.SetWallpaper(mid, red)
dw.SetPosition(wallpaper.DWPOS_FILL)
time.sleep(1.6)


def sample():
    return ImageGrab.grab(bbox=(SX, SY, SX + 1, SY + 1)).convert("RGB").getpixel((0, 0))


print("起始:", sample())
blue_img = Image.new("RGB", (W, H), (30, 30, 200))
traj = []
done = threading.Event()


def run_fade():
    ovs = fade.crossfade([(0, 0, W, H, blue_img)], duration_ms=300, fps=60)
    time.sleep(0.12)
    fade.destroy_all(ovs)
    done.set()


t = threading.Thread(target=run_fade, daemon=True)
t.start()
t0 = time.perf_counter()
while not done.is_set() and time.perf_counter() - t0 < 3:
    traj.append((round((time.perf_counter() - t0) * 1000), sample()))
    time.sleep(0.02)

mids = [(ms, c) for ms, c in traj if 60 < c[0] < 170]
print("采样帧数:", len(traj))
print("前 10 帧:", traj[:10])
print("中间色帧数:", len(mids))
print("结果:", "淡入生效" if len(mids) >= 3 else "没有过渡")
try:
    os.remove(red)
    os.rmdir(OUT)
except OSError:
    pass
