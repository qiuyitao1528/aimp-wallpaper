# -*- coding: utf-8 -*-
"""复现退出链路：Widget(钉桌面) + VisPanel 构建后调 _quit，看 config.save / destroy 谁出问题。
只起 UI，不碰壁纸渲染、不碰 AIMP 通知。带看门狗，卡死自动退出。"""
import os
import sys
import threading
import time

sys.path.insert(0, r"E:\aimp-wallpaper")

import tkinter as tk

from aimp_wallpaper import config
from aimp_wallpaper.aimp_api import AimpIPC
from aimp_wallpaper.vis_panel import VisPanel
from aimp_wallpaper.widget import Widget


def watchdog(seconds):
    def _fire():
        print(f"!! 看门狗：{seconds}s 后 mainloop 仍未退出 —— destroy 卡死", flush=True)
        os._exit(9)
    t = threading.Timer(seconds, _fire)
    t.daemon = True
    t.start()


def main():
    cfg = config.load()
    ipc = AimpIPC()  # 不 start()：不建通知窗口，_tick 用 snapshot 即可
    root = tk.Tk()
    widget = Widget(root, ipc, cfg, show_vis=lambda: None)
    panel = VisPanel(root, cfg)

    def probe():
        print("T+3s: 调 widget._quit()（存位置→config.save→root.destroy）", flush=True)
        t0 = time.perf_counter()
        try:
            widget._quit()
            print(f"_quit 返回，耗时 {(time.perf_counter()-t0)*1000:.0f}ms，等 mainloop 退出", flush=True)
        except Exception:
            import traceback
            traceback.print_exc()
            os._exit(8)

    watchdog(10)
    root.after(3000, probe)
    root.mainloop()
    print("MAINLOOP 正常退出 ✓", flush=True)


if __name__ == "__main__":
    main()
