# -*- coding: utf-8 -*-
"""控件 ULW 调试：surface 状态、update 返回值、DIB 内容读回。"""
import sys
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import tkinter as tk

from aimp_wallpaper import config
from aimp_wallpaper.aimp_api import AimpIPC
from aimp_wallpaper.widget import Widget


def main():
    cfg = config.load()
    ipc = AimpIPC()
    root = tk.Tk()
    w = Widget(root, ipc, cfg, show_vis=lambda: None)
    root.update_idletasks()
    print("surface.ok:", w.surface.ok)
    print("surface arr alpha 均值:", round(float(w.surface.arr[..., 3].mean()), 1),
          "max:", int(w.surface.arr[..., 3].max()))
    ok = w.surface.update(w._img, pos=w._screen_pos())
    print("update 返回:", ok)
    print("窗口 rect:", w._screen_pos(), "W×H:", w.W, w.H)
    root.after(1500, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
