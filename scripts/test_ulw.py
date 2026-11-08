# -*- coding: utf-8 -*-
"""ULW 尖峰测试：顶层 Tk 窗口 + OverlaySurface，画白方块 → 截屏区域做像素验证。
不读任何图像进上下文，纯 numpy 数值断言。"""
import sys
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import numpy as np
import tkinter as tk
from PIL import Image, ImageDraw

from aimp_wallpaper import desktop

W, H = 300, 100

root = tk.Tk()
root.overrideredirect(True)
root.geometry(f"+200+200")
root.configure(bg="black")
root.update_idletasks()
hwnd = desktop.user32.GetAncestor(desktop.HWND_T(root.winfo_id()), desktop.GA_ROOT)
desktop.style_overlay_window(hwnd)

surf = desktop.OverlaySurface(hwnd, W, H)
print("surface ok:", surf.ok)

img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.rectangle((40, 30, 159, 69), fill=(255, 255, 255, 255))
ok1 = surf.update(img)
root.update()
print("ULW 第一次:", ok1)


def grab():
    from PIL import ImageGrab
    return np.asarray(ImageGrab.grab(bbox=(200, 200, 200 + W, 200 + H)).convert("RGB"))


a = grab()
mid = a[30:70, 60:140]
corner = a[0:15, 0:15]
print("方块区均值(应~255):", float(mid.mean()), "| 角落均值(应~0):", float(corner.mean()))
assert mid.mean() > 240, "方块没上屏"
assert corner.mean() < 8, "透明区不透明"

# 动一下：方块移位，验证动画呈现
img2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d2 = ImageDraw.Draw(img2)
d2.rectangle((140, 30, 259, 69), fill=(255, 255, 255, 255))
print("ULW 第二次:", surf.update(img2))
root.update()
b = grab()
left = b[30:70, 60:120]
right = b[30:70, 160:240]
print("移位后左区(应~0):", float(left.mean()), "| 右区(应~255):", float(right.mean()))
assert left.mean() < 8 and right.mean() > 240, "ULW 动画更新失败"

print("ULW 尖峰测试: 全部通过")
surf.close()
root.destroy()
