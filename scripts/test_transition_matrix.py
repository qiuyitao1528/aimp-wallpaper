# -*- coding: utf-8 -*-
"""变量矩阵：找出什么条件下 Windows 会给壁纸渐变过渡。
每组：先设红，再设蓝，15ms 采样 1.2s，统计"中间色"帧数。"""
import ctypes
import io
import os
import sys
import time

import comtypes
from PIL import Image, ImageGrab

sys.path.insert(0, r"E:\aimp-wallpaper")
from aimp_wallpaper import wallpaper

comtypes.CoInitialize()
OUT = os.path.join(os.environ["LOCALAPPDATA"], "aimp-wallpaper", "_anim")
os.makedirs(OUT, exist_ok=True)
SX, SY = 500, 300


def sample():
    return ImageGrab.grab(bbox=(SX, SY, SX + 1, SY + 1)).convert("RGB").getpixel((0, 0))


def save(color, path, fmt):
    im = Image.new("RGB", (1920, 1080), color)
    if fmt == "PNG":
        im.save(path, "PNG")
    else:
        im.save(path, "JPEG", quality=92)


def run(label, fmt="PNG", same_path=True, set_position=True, setter="com"):
    dw = wallpaper._get_wallpaper_com()
    mid = dw.GetMonitorDevicePathAt(0)
    p1 = os.path.join(OUT, "w1." + ("png" if fmt == "PNG" else "jpg"))
    p2 = p1 if same_path else os.path.join(OUT, "w2." + ("png" if fmt == "PNG" else "jpg"))

    def apply(path):
        if setter == "com":
            dw.SetWallpaper(mid, path)
            if set_position:
                dw.SetPosition(wallpaper.DWPOS_FILL)
        else:
            user32 = ctypes.WinDLL("user32")
            user32.SystemParametersInfoW(0x0014, 0, path, 0x01 | 0x02)

    save((200, 30, 30), p1, fmt)
    apply(p1)
    time.sleep(1.6)
    save((30, 30, 200), p2, fmt)
    apply(p2)
    t0 = time.perf_counter()
    traj = []
    while time.perf_counter() - t0 < 1.2:
        traj.append((round((time.perf_counter() - t0) * 1000), sample()))
        time.sleep(0.015)
    mids = [(ms, c) for ms, c in traj if abs(c[0] - 200) > 20 and abs(c[0] - 30) > 20]
    print(f"{label:<38} 过渡帧={len(mids):<3} 采样帧={len(traj):<3} 终值={traj[-1][1]}")
    return len(mids)


results = {}
results["PNG 同路径 + SetPosition"] = run("PNG 同路径 + SetPosition")
results["PNG 新路径 + SetPosition"] = run("PNG 新路径 + SetPosition", same_path=False)
results["JPEG 同路径 + SetPosition"] = run("JPEG 同路径 + SetPosition", fmt="JPEG")
results["JPEG 新路径 + SetPosition"] = run("JPEG 新路径 + SetPosition", fmt="JPEG", same_path=False)
results["PNG 同路径 不调SetPosition"] = run("PNG 同路径 不调SetPosition", set_position=False)
results["SAPI PNG 同路径"] = run("SAPI PNG 同路径", setter="sapi")

print("\n有过渡的组合:", [k for k, v in results.items() if v] or "无")
