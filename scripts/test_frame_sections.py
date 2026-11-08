# -*- coding: utf-8 -*-
"""分段计时：>40ms 的帧拆解为 快照/绘制循环/帧间空白，定位卡顿归属。"""
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
    stats = {"n": 0, "slow": [], "sec": {"snap": 0.0, "loop": 0.0, "other": 0.0}}
    last = {"t": None}

    orig_interp = VisPanel._frame

    def timed_frame(self):
        t0 = time.perf_counter()
        a = time.perf_counter()
        target, prev_t, t_prev, t_curr = self.spec.interp_snapshot()
        b = time.perf_counter()
        # 手动内联原渲染（拆段计时），替换掉原 _frame
        self._tick_n += 1
        if self._tick_n % 30 == 1:
            self._seat_above_desktop()
            self._follow_anchor()
        c = self.canvas
        if self.spec.err:
            c.after(1000, lambda: timed_frame(self))
            return
        now = time.monotonic()
        span = max(t_curr - t_prev, 1e-3)
        alpha = max(0.0, min(1.0, (now - t_prev) / span))
        smooth = prev_t[:self.n_bands] + (target[:self.n_bands] - prev_t[:self.n_bands]) * alpha
        self._disp = np_maximum(smooth, self._disp * 0.81)
        cy = self.H // 2
        ymax = (self.H // 2) - self.pad - int(2 * self.s)
        dot_h = max(1, int(self.s))
        geom = self._geom
        n_coords = 0
        for i, (x, w) in enumerate(self._layout):
            h = int(min(1.0, max(0.0, float(self._disp[i]))) * ymax)
            self._peaks[i] = max(self._peaks[i] * 0.99 - 0.0024, h / max(1, ymax))
            pi = int(self._peaks[i] * ymax)
            if h >= 1:
                if geom[i, 0] <= 0:
                    c.itemconfig(self._items_bar[i], state="normal")
                    geom[i, 0] = h
                    c.coords(self._items_bar[i], x, cy - h, x + w, cy + h)
                    n_coords += 1
                elif geom[i, 0] != h:
                    geom[i, 0] = h
                    c.coords(self._items_bar[i], x, cy - h, x + w, cy + h)
                    n_coords += 1
            elif geom[i, 0] > 0:
                geom[i, 0] = 0
                c.itemconfig(self._items_bar[i], state="hidden")
            if pi >= 1:
                if geom[i, 1] <= 0:
                    c.itemconfig(self._items_pk[i][0], state="normal")
                    c.itemconfig(self._items_pk[i][1], state="normal")
                    geom[i, 1] = pi
                    c.coords(self._items_pk[i][0], x, cy - pi - dot_h, x + w, cy - pi)
                    c.coords(self._items_pk[i][1], x, cy + pi, x + w, cy + pi + dot_h)
                    n_coords += 2
                elif geom[i, 1] != pi:
                    geom[i, 1] = pi
                    c.coords(self._items_pk[i][0], x, cy - pi - dot_h, x + w, cy - pi)
                    c.coords(self._items_pk[i][1], x, cy + pi, x + w, cy + pi + dot_h)
                    n_coords += 2
            elif geom[i, 1] > 0:
                geom[i, 1] = 0
                c.itemconfig(self._items_pk[i][0], state="hidden")
                c.itemconfig(self._items_pk[i][1], state="hidden")
        c2 = time.perf_counter()
        total = (c2 - t0) * 1000
        stats["sec"]["snap"] += (b - a) * 1000
        stats["sec"]["loop"] += (c2 - b) * 1000
        stats["sec"]["other"] += max(0.0, total - (b - a) * 1000 - (c2 - b) * 1000)
        now2 = time.perf_counter()
        if last["t"] is not None:
            delta = (now2 - last["t"]) * 1000
            stats["n"] += 1
            if delta > 40:
                stats["slow"].append((delta, total, n_coords))
        last["t"] = now2
        self.win.after(max(5, 33 - int(total)), lambda: timed_frame(self))

    VisPanel._frame = timed_frame

    import numpy as np
    np_maximum = np.maximum
    globals()["np_maximum"] = np_maximum

    def _shown_gate(self, *a):
        pass
    globals()["np_maximum"] = np_maximum

    def show_vis():
        if panel["obj"] is None:
            panel["obj"] = VisPanel(root, cfg)

    if not cfg.get("vis_hidden"):
        try:
            panel["obj"] = VisPanel(root, cfg)
        except Exception:
            traceback.print_exc()
    Widget(root, ipc, cfg, show_vis=show_vis)

    cpu0 = time.process_time()
    t0 = time.perf_counter()

    def report():
        wall = time.perf_counter() - t0
        cpu = (time.process_time() - cpu0) / wall * 100
        sec = stats["sec"]
        print(f"帧数={stats['n']} | CPU={cpu:.1f}% | 分段累计: 快照 {sec['snap']:.0f}ms "
              f"绘制循环 {sec['loop']:.0f}ms 其他 {sec['other']:.0f}ms", flush=True)
        for delta, total, nc in stats["slow"][-8:]:
            print(f"  慢帧: 帧间 {delta:.0f}ms / 本帧工作 {total:.1f}ms / coords {nc}", flush=True)
        root.after(12000, report)

    root.after(12000, report)
    root.after(24000, lambda: (report(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
