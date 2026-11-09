# -*- coding: utf-8 -*-
"""方案B 验证：过渡轨迹无闪回 + 覆盖层存在时长（=图标被盖时长）。"""
import os
import sys
import threading
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import comtypes
from PIL import Image, ImageGrab

from aimp_wallpaper import fade, wallpaper

OUT = os.path.join(os.environ["LOCALAPPDATA"], "aimp-wallpaper", "_fo2")
os.makedirs(OUT, exist_ok=True)
W, H = 1920, 1080
red_p, blue_p = os.path.join(OUT, "red.png"), os.path.join(OUT, "blue.png")
Image.new("RGB", (W, H), (200, 30, 30)).save(red_p, "PNG")
Image.new("RGB", (W, H), (30, 30, 200)).save(blue_p, "PNG")

comtypes.CoInitialize()
dw = wallpaper._get_wallpaper_com()
mid = dw.GetMonitorDevicePathAt(0)
dw.SetWallpaper(mid, red_p)
dw.SetPosition(wallpaper.DWPOS_FILL)
time.sleep(1.6)


def pick_point():
    for y in range(200, 1000, 60):
        for x in range(300, 1800, 60):
            if ImageGrab.grab(bbox=(x, y, x + 1, y + 1)).convert("RGB").getpixel((0, 0)) == (200, 30, 30):
                return x, y
    return None


pt = pick_point()
print("采样点:", pt)
traj, stop = [], threading.Event()


def sampler():
    t0 = time.perf_counter()
    while not stop.is_set():
        c = ImageGrab.grab(bbox=(pt[0], pt[1], pt[0] + 1, pt[1] + 1)).convert("RGB").getpixel((0, 0))
        traj.append((round((time.perf_counter() - t0) * 1000), c))
        time.sleep(0.02)


threading.Thread(target=sampler, daemon=True).start()
time.sleep(0.12)

old_img, new_img = Image.open(red_p).convert("RGB"), Image.open(blue_p).convert("RGB")
t_create = time.perf_counter()
ovs = fade.crossfade_create([(0, 0, W, H, old_img)], [(0, 0, W, H, new_img)])
dw.SetWallpaper(mid, blue_p)
dw.SetPosition(wallpaper.DWPOS_FILL)
fade.crossfade_run(ovs, 220)
painted = fade.wait_painted(ovs)
t_destroy = time.perf_counter()
fade.destroy_all(ovs)
time.sleep(0.3)
stop.set()

print(f"覆盖层存在 {(t_destroy - t_create) * 1000:.0f}ms | 撤层时桌面已刷上新图: {painted}")
print("轨迹(每 3 帧):")
for ms, c in traj[::3]:
    print(f"  {ms:>4}ms  {c}")
blues = [i for i, (_m, c) in enumerate(traj) if c[2] > 150]
flash = any(traj[i][1][0] > 150 for i in range(blues[2], len(traj))) if len(blues) >= 3 else False
print("蓝色帧:", len(blues), "| 变蓝后回红:", flash)
print("结果:", "过渡平滑且无闪回" if blues and not flash else "仍有问题")
for f in (red_p, blue_p):
    try:
        os.remove(f)
    except OSError:
        pass
try:
    os.rmdir(OUT)
except OSError:
    pass
