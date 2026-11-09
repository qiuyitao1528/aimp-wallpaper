# -*- coding: utf-8 -*-
"""验证旧图淡出：红→蓝 不应出现"变蓝后又闪回红"。
主线程做过渡（COM 同线程），另一线程只采屏（不需要 COM）。"""
import os
import sys
import threading
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import comtypes
from PIL import Image, ImageGrab

from aimp_wallpaper import fade, wallpaper

OUT = os.path.join(os.environ["LOCALAPPDATA"], "aimp-wallpaper", "_fo")
os.makedirs(OUT, exist_ok=True)
SX, SY = 500, 300
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

traj, stop = [], threading.Event()


def sampler():
    t0 = time.perf_counter()
    while not stop.is_set():
        c = ImageGrab.grab(bbox=(SX, SY, SX + 1, SY + 1)).convert("RGB").getpixel((0, 0))
        traj.append((round((time.perf_counter() - t0) * 1000), c))
        time.sleep(0.02)


s = threading.Thread(target=sampler, daemon=True)
s.start()
time.sleep(0.15)

old_img = Image.open(red_p).convert("RGB")
ovs = fade.show_snapshot([(0, 0, W, H, old_img)])
try:
    dw.SetWallpaper(mid, blue_p)
    dw.SetPosition(wallpaper.DWPOS_FILL)
    time.sleep(0.45)
    fade.fade_out(ovs, 220)
finally:
    fade.destroy_all(ovs)
time.sleep(0.25)
stop.set()
s.join(1)

print("轨迹(每 3 帧):")
for ms, c in traj[::3]:
    print(f"  {ms:>4}ms  {c}")
blues = [i for i, (_ms, c) in enumerate(traj) if c[2] > 150]
flash = False
if len(blues) >= 3:
    flash = any(traj[i][1][0] > 150 for i in range(blues[2], len(traj)))
print("蓝色帧数:", len(blues), "| 变蓝后又回红:", flash)
print("结果:", "过渡正常且无闪回" if blues and not flash else "仍有问题")
for f in (red_p, blue_p):
    try:
        os.remove(f)
    except OSError:
        pass
try:
    os.rmdir(OUT)
except OSError:
    pass
