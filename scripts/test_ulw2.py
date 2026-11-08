# -*- coding: utf-8 -*-
"""ULW 调试 v2：整屏扫描定位白方块实际落点 + 前后对比。"""
import sys
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import numpy as np
import tkinter as tk
from PIL import Image, ImageDraw, ImageGrab

from aimp_wallpaper import desktop

W, H = 300, 100
X, Y = 200, 200

root = tk.Tk()
root.overrideredirect(True)
root.geometry(f"+{X}+{Y}")
root.configure(bg="black")
root.update_idletasks()
hwnd = desktop.user32.GetAncestor(desktop.HWND_T(root.winfo_id()), desktop.GA_ROOT)
desktop.style_overlay_window(hwnd)
desktop.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x2 | 0x1 | 0x10)  # TOPMOST（测试窗口要可见）

surf = desktop.OverlaySurface(hwnd, W, H)
img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.rectangle((40, 30, 159, 69), fill=(255, 255, 255, 255))


def shot():
    from PIL import ImageGrab
    a = np.asarray(ImageGrab.grab().convert("RGB"))
    return a


# 基线：窗口存在但还没 ULW
root.update()
base = shot()
print("屏幕尺寸:", base.shape[1], "x", base.shape[0])

ok = surf.update(img)
root.update()
after = shot()
print("ULW:", ok)

diff = (np.abs(base.astype(int) - after.astype(int)).sum(axis=2) > 10)
ys, xs = np.nonzero(diff)
if len(xs):
    print(f"变化区域: x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}] 像素数={len(xs)}")
    px = after[ys, xs]
    print("变化处颜色样本:", px[:3].tolist())
else:
    print("整屏无任何变化！")
