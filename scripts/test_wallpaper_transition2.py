# -*- coding: utf-8 -*-
"""对比：SystemParametersInfo(SPI_SETDESKWALLPAPER) 是否带渐变过渡。"""
import ctypes
import os
import time

import comtypes
from PIL import Image, ImageGrab

import sys
sys.path.insert(0, r"E:\aimp-wallpaper")
from aimp_wallpaper import wallpaper

comtypes.CoInitialize()
out = os.path.join(os.environ["LOCALAPPDATA"], "aimp-wallpaper", "_animtest2")
os.makedirs(out, exist_ok=True)
SX, SY = 500, 300
user32 = ctypes.WinDLL("user32", use_last_error=True)
SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATEINIFILE, SPIF_SENDWININICHANGE = 0x01, 0x02


def sample():
    return ImageGrab.grab(bbox=(SX, SY, SX + 1, SY + 1)).convert("RGB").getpixel((0, 0))


def set_sapi(color, name):
    path = os.path.join(out, name)
    Image.new("RGB", (1920, 1080), color).save(path, "PNG")
    user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, path,
                                 SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE)


def set_com(color, name):
    path = os.path.join(out, name)
    Image.new("RGB", (1920, 1080), color).save(path, "PNG")
    dw = wallpaper._get_wallpaper_com()
    dw.SetWallpaper(dw.GetMonitorDevicePathAt(0), path)
    dw.SetPosition(wallpaper.DWPOS_FILL)


def measure(setter, label):
    setter((200, 30, 30), "red.png")
    time.sleep(1.6)
    setter((30, 30, 200), "blue.png")
    t0 = time.perf_counter()
    traj = []
    while time.perf_counter() - t0 < 1.5:
        traj.append((round((time.perf_counter() - t0) * 1000), sample()))
        time.sleep(0.025)
    mids = [(ms, c) for ms, c in traj
            if abs(c[0] - 200) > 25 and abs(c[0] - 30) > 25]
    print(f"[{label}] 过渡帧数={len(mids)} 终值={traj[-1][1]}")
    if mids:
        print("   过渡样本:", mids[:6])
    return len(mids)


a = measure(set_com, "COM IDesktopWallpaper")
b = measure(set_sapi, "SystemParametersInfo")
print("\n结论:", f"COM过渡帧={a}, SAPI过渡帧={b}")
print("有过渡动画" if (a or b) else "两者都无过渡")
