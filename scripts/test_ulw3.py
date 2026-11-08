# -*- coding: utf-8 -*-
"""ULW 调试 v3：读回 DIB 验证写入 + 窗口尺寸 + ULW 变体矩阵。"""
import ctypes
import sys
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import numpy as np
import tkinter as tk
from PIL import Image, ImageDraw

from aimp_wallpaper import desktop

W, H = 300, 100
X, Y = 200, 200

root = tk.Tk()
root.overrideredirect(True)
root.geometry(f"+{X}+{Y}")
root.configure(bg="black")
root.update_idletasks()
root.update()
print("Tk 窗口实际尺寸:", root.winfo_width(), "x", root.winfo_height())

hwnd = desktop.user32.GetAncestor(desktop.HWND_T(root.winfo_id()), desktop.GA_ROOT)
desktop.style_overlay_window(hwnd)
desktop.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x2 | 0x1 | 0x10)

surf = desktop.OverlaySurface(hwnd, W, H)
img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.rectangle((40, 30, 159, 69), fill=(255, 255, 255, 255))

# 预乘写入（复刻 update 的写入逻辑）到 surf.arr
a = np.asarray(img)
alpha = a[..., 3:4].astype(np.uint16)
surf.arr[..., 0] = a[..., 2] * alpha[..., 0] // 255
surf.arr[..., 1] = a[..., 1] * alpha[..., 0] // 255
surf.arr[..., 2] = a[..., 0] * alpha[..., 0] // 255
surf.arr[..., 3] = a[..., 3]
print("DIB 读回: 方块alpha均值=", float(surf.arr[30:70, 40:160, 3].mean()),
      "| 角落alpha均值=", float(surf.arr[0:15, 0:15, 3].mean()))

# 变体矩阵
def shot():
    from PIL import ImageGrab
    return np.asarray(ImageGrab.grab(bbox=(X, Y, X + W, Y + H)).convert("RGB"))

pt = desktop.wintypes.POINT(0, 0)
size = desktop.SIZE(W, H)
variants = [
    ("NULL/NULL/NULL", dict(hdcDst=None, pptDst=None, psize=None)),
    ("显式位置尺寸", dict(hdcDst=None, pptDst=desktop.wintypes.POINT(X, Y), psize=size)),
]
for name, kw in variants:
    hd = kw.get("hdcDst")
    pd = kw.get("pptDst")
    ps = kw.get("psize")
    ok = bool(desktop.user32.UpdateLayeredWindow(
        desktop.HWND_T(hwnd), hd,
        ctypes.byref(pd) if pd else None,
        ctypes.byref(ps) if ps else None,
        surf.hdc, ctypes.byref(pt), 0, ctypes.byref(surf.blend), desktop.ULW_ALPHA))
    root.update()
    time.sleep(0.3)
    s = shot()
    mid = float(s[30:70, 40:160].mean())
    corner = float(s[0:15, 0:15].mean())
    print(f"{name}: ULW={ok} 方块区={mid:.0f} 角落={corner:.0f}")
