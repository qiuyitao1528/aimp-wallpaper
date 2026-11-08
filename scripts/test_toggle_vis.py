# -*- coding: utf-8 -*-
"""phase2 插桩版：逐段定位 VisPanel.__init__ 卡点。"""
import os
import sys
import threading
import time
import traceback

sys.path.insert(0, r"E:\aimp-wallpaper")

import tkinter as tk

from aimp_wallpaper import config, desktop
from aimp_wallpaper.aimp_api import AimpIPC
from aimp_wallpaper.audio_spectrum import Spectrum
from aimp_wallpaper.vis_panel import VisPanel
from aimp_wallpaper.widget import Widget


def watchdog(seconds):
    def _fire():
        print(f"!! 看门狗：{seconds}s 未结束 => 主线程卡死确认", flush=True)
        os._exit(9)
    threading.Timer(seconds, _fire).start()


def probe(mod, name):
    orig = getattr(mod, name)

    def wrapped(*a, **kw):
        print(f"  -> {name} ...", flush=True)
        t0 = time.perf_counter()
        r = orig(*a, **kw)
        print(f"  <- {name} {(time.perf_counter()-t0)*1000:.0f}ms", flush=True)
        return r
    setattr(mod, name, wrapped)


def main():
    cfg = config.load()
    assert cfg.get("vis_hidden"), "dev config 应处于 vis_hidden=True（先跑 phase1）"
    ipc = AimpIPC()
    root = tk.Tk()
    panel = {"obj": None}

    # 插桩：构造链路每一步
    probe(desktop, "style_desktop_widget")
    probe(VisPanel, "_place_initial")
    probe(VisPanel, "_seat_above_desktop")
    probe(Spectrum, "start")
    _orig_upd = tk.Toplevel.update_idletasks

    def upd(self):
        print("  -> update_idletasks ...", flush=True)
        _orig_upd(self)
        print("  <- update_idletasks", flush=True)
    tk.Toplevel.update_idletasks = upd

    def show_vis():
        print("show_vis 调用", flush=True)
        if panel["obj"] is None:
            try:
                panel["obj"] = VisPanel(root, cfg)
                print("VisPanel 创建 OK", flush=True)
            except Exception:
                traceback.print_exc()
                return
        else:
            panel["obj"].show()
        cfg["vis_hidden"] = False
        config.save(cfg)

    def toggle_vis():
        print("toggle_vis 触发", flush=True)
        p = panel["obj"]
        if p is None or cfg.get("vis_hidden"):
            show_vis()
        else:
            p.hide()

    Widget(root, ipc, cfg, show_vis=show_vis)

    def fake_tray():
        time.sleep(3)
        print("伪托盘线程：root.after(0, toggle_vis)", flush=True)
        root.after(0, toggle_vis)
        print("伪托盘线程：after 已排队返回", flush=True)
    threading.Thread(target=fake_tray, daemon=True, name="fake-tray").start()
    watchdog(18)
    root.mainloop()
    print("MAINLOOP 退出", flush=True)


if __name__ == "__main__":
    main()
