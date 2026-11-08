# -*- coding: utf-8 -*-
"""帧率/卡顿基线测量：跑 12s，统计 _frame 实际间隔 p50/p95/max + 进程 CPU 占用。"""
import os
import sys
import time
import traceback

sys.path.insert(0, r"E:\aimp-wallpaper")

import tkinter as tk

from aimp_wallpaper import config
from aimp_wallpaper.aimp_api import AimpIPC
from aimp_wallpaper.vis_panel import VisPanel
from aimp_wallpaper.widget import Widget


def main():
    cfg = config.load()
    ipc = AimpIPC()
    root = tk.Tk()
    panel = {"obj": None}

    def show_vis():
        if panel["obj"] is None:
            panel["obj"] = VisPanel(root, cfg)

    if not cfg.get("vis_hidden"):
        try:
            panel["obj"] = VisPanel(root, cfg)
        except Exception:
            traceback.print_exc()
    Widget(root, ipc, cfg, show_vis=show_vis)

    deltas = []
    last = {"t": None}
    orig_frame = VisPanel._frame

    def timed_frame(self):
        now = time.perf_counter()
        if last["t"] is not None:
            deltas.append(((now - last["t"]) * 1000, self._tick_n))
        last["t"] = now
        orig_frame(self)

    VisPanel._frame = timed_frame  # 类级补丁：创建的面板 after 链自动走包装版
    cpu0 = time.process_time()
    t0 = time.perf_counter()

    def report():
        wall = time.perf_counter() - t0
        cpu = (time.process_time() - cpu0) / wall * 100
        if deltas:
            ds = sorted(deltas[5:])
            n = len(ds)
            print(f"帧数={n} p50={ds[n // 2][0]:.1f}ms p95={ds[int(n * 0.95)][0]:.1f}ms "
                  f"max={ds[-1][0]:.1f}ms | CPU占用={cpu:.1f}%", flush=True)
            spikes = [d for d in deltas[5:] if d[0] > 60]
            for d, tick in spikes[-6:]:
                print(f"  尖峰 {d:.0f}ms @tick {tick} (相位 {tick % 30}/30)", flush=True)
        root.after(12000, report)

    root.after(12000, report)
    root.after(24000, lambda: (report(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
