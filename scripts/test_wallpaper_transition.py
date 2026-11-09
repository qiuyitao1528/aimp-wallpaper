# -*- coding: utf-8 -*-
"""实测：SetWallpaper 换图时 Windows 是否有渐变过渡。
对比：同一文件名覆盖 vs 每次用新文件名。"""
import os
import sys
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import comtypes
from PIL import Image, ImageGrab

from aimp_wallpaper import wallpaper

comtypes.CoInitialize()
dw = wallpaper._get_wallpaper_com()
mid = dw.GetMonitorDevicePathAt(0)
out = os.path.join(os.environ["LOCALAPPDATA"], "aimp-wallpaper", "_animtest")
os.makedirs(out, exist_ok=True)

# 采样点：屏幕中部偏下（避开频谱面板区域）
SX, SY = 500, 300


def sample():
    return ImageGrab.grab(bbox=(SX, SY, SX + 1, SY + 1)).convert("RGB").getpixel((0, 0))


def set_img(color, path):
    Image.new("RGB", (1920, 1080), color).save(path, "PNG")
    dw.SetWallpaper(mid, path)
    dw.SetPosition(wallpaper.DWPOS_FILL)


def measure(second_color, path2, label):
    """设成红，再设成 second_color，记录 1.2 秒内的颜色轨迹。"""
    set_img((200, 30, 30), os.path.join(out, "a.png"))
    time.sleep(1.5)
    before = sample()
    set_img(second_color, path2)
    t0 = time.perf_counter()
    traj = []
    while time.perf_counter() - t0 < 1.2:
        traj.append((round((time.perf_counter() - t0) * 1000), sample()))
        time.sleep(0.03)
    # 判断：有没有出现"中间色"（红→目标之间）
    mid_steps = []
    for ms, c in traj:
        r, g, b = c
        if abs(r - 200) > 25 and abs(r - second_color[0]) > 25:
            mid_steps.append((ms, c))
    print(f"[{label}] 起点={before} 终点={traj[-1][1]} 中间过渡帧数={len(mid_steps)}")
    if mid_steps:
        print("   过渡样本:", mid_steps[:5])
    print("   轨迹前 8 帧:", traj[:8])
    return len(mid_steps)


n1 = measure((30, 30, 200), os.path.join(out, "b_same.png"), "同一路径覆盖")
n2 = measure((30, 30, 200), os.path.join(out, "b_new_%d.png" % int(time.time())), "每次新文件名")
print("\n结论：", "有过渡动画" if (n1 > 0 or n2 > 0) else "无过渡（瞬间切换）")
