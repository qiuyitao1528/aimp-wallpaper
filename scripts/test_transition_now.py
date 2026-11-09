# -*- coding: utf-8 -*-
"""重测：Windows 自身是否又给壁纸渐变（自动挑真正露出的桌面点）。"""
import os
import sys
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import comtypes
from PIL import Image, ImageGrab

from aimp_wallpaper import wallpaper

comtypes.CoInitialize()
OUT = os.path.join(os.environ["LOCALAPPDATA"], "aimp-wallpaper", "_t3")
os.makedirs(OUT, exist_ok=True)
W, H = 1920, 1080
red_p, blue_p = os.path.join(OUT, "r.png"), os.path.join(OUT, "b.png")
Image.new("RGB", (W, H), (200, 30, 30)).save(red_p, "PNG")
Image.new("RGB", (W, H), (30, 30, 200)).save(blue_p, "PNG")
dw = wallpaper._get_wallpaper_com()
mid = dw.GetMonitorDevicePathAt(0)


def px(x, y):
    return ImageGrab.grab(bbox=(x, y, x + 1, y + 1)).convert("RGB").getpixel((0, 0))


dw.SetWallpaper(mid, red_p)
dw.SetPosition(wallpaper.DWPOS_FILL)
time.sleep(1.8)

pt = None
for y in range(150, 1000, 50):
    for x in range(250, 1850, 50):
        if px(x, y) == (200, 30, 30):
            pt = (x, y)
            break
    if pt:
        break
print("采样点:", pt)
if not pt:
    print("找不到露出的桌面区域，无法测量")
    raise SystemExit

dw.SetWallpaper(mid, blue_p)
dw.SetPosition(wallpaper.DWPOS_FILL)
t0 = time.perf_counter()
traj = []
while time.perf_counter() - t0 < 1.5:
    traj.append((round((time.perf_counter() - t0) * 1000), px(*pt)))
    time.sleep(0.02)

mids = [(ms, c) for ms, c in traj if 60 < c[0] < 175]
print("中间色帧:", len(mids))
for ms, c in traj[::2][:14]:
    print(f"  {ms:>4}ms {c}")
print("结论:", "Windows 自身有渐变" if len(mids) >= 3 else "Windows 仍是硬切")
for f in (red_p, blue_p):
    try:
        os.remove(f)
    except OSError:
        pass
try:
    os.rmdir(OUT)
except OSError:
    pass
