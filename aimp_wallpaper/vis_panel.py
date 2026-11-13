"""可视化面板：桌面右下角实时频谱，AIMP 经典样式——

- 渲染走 UpdateLayeredWindow 逐像素 alpha（微软推荐动画路线）：PIL 画帧 →
  预乘 BGRA → 原子呈现，绕开 GUI 工具包重绘路径，无闪烁、无色键锯齿
- 条形以水平中轴上下对称；白色细条 + 点状峰值帽；无声列完全隐藏
- 数据 47Hz（WASAPI 环回 FFT）与显示 30fps 之间做时间线性插值，运动连续

窗口定位沿用实测路线：顶层窗口 + SetWindowPos 把 Progman 压到窗口下方。
UpdateLayeredWindow 不可用时自动回退到画布 + 色键的旧路径。
"""
from __future__ import annotations

import json
import os
import sys
import time
import tkinter as tk
from ctypes import byref

import numpy as np
from PIL import Image, ImageDraw

from . import applog, config, desktop, wallpaper
from .audio_spectrum import Spectrum

_BAR = (255, 255, 255, 255)
_PEAK = (255, 255, 255, 255)
FRAME_MS_DEFAULT = 33   # 默认 30fps：频谱数据 ~47Hz，插值后已平滑
BAR_FALL_SEC = 0.81 ** 30   # 条衰减/秒（等效 30fps 下的 0.81/帧）
PEAK_MULT_SEC = 0.99 ** 30  # 峰值帽指数衰减/秒
PEAK_DROP_SEC = 0.0024 * 30  # 峰值帽线性下坠/秒


class VisPanel:
    def __init__(self, root: tk.Tk, cfg: dict):
        self.cfg = cfg
        dpi = desktop.user32.GetDpiForSystem() or 96
        self.s = dpi / 96.0
        self.W = int(cfg.get("vis_width", 420) * self.s)
        self.H = int(cfg.get("vis_height", 120) * self.s)
        self.pad = int(4 * self.s)

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.resizable(False, False)
        self.win.configure(bg=desktop.KEY_HEX)
        # 画布仅作 ULW 不可用时的回退渲染面（ULW 模式下其内容不参与显示）
        self.canvas = tk.Canvas(self.win, width=self.W, height=self.H,
                                bg=desktop.KEY_HEX, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.win.bind("<Button-1>", self._drag_start)
        self.win.bind("<B1-Motion>", self._drag_move)
        self.win.bind("<ButtonRelease-1>", self._drag_end)
        self.win.bind("<Button-3>", self._popup)

        self.menu = tk.Menu(self.win, tearoff=0)
        self.menu.add_command(label="设置…", command=self._open_settings)
        self.menu.add_command(label="跟随壁纸位置", command=self._reset_pos)
        self._lock_var = tk.BooleanVar(value=bool(self.cfg.get("vis_locked")))
        self.menu.add_checkbutton(label="锁定（禁拖动）", variable=self._lock_var,
                                  command=self._toggle_lock)
        self.menu.add_separator()
        self.menu.add_command(label="隐藏面板", command=self.hide)
        self.menu.add_command(label="退出", command=self._quit)

        self._status_font = wallpaper._load_font(False, int(10 * self.s), "segoeui.ttf")[0]
        self._status_text = "正在接入系统声音…"

        self._layout = self._compute_layout()  # [(x, w), ...]
        self.n_bands = len(self._layout)
        self._peaks = np.zeros(self.n_bands)
        self._disp = np.zeros(self.n_bands)          # UI 层包络值
        self.frame_ms = FRAME_MS_DEFAULT             # 由 vis_fps 设置驱动
        self._geom = np.zeros((self.n_bands, 2), dtype=int)  # 画布路径的 [h, p] 缓存
        self._canvas_items_ready = False
        self._drag = None
        self._tick_n = 0
        self._anchor_cache = None
        self._anchor_cache_mtime = None

        self.spec = Spectrum(n_bands=self.n_bands, f_max=cfg.get("vis_fmax", 16000))
        self.spec.start()

        self._place_initial()
        self.win.update_idletasks()
        hwnd = desktop.user32.GetAncestor(desktop.HWND_T(self.win.winfo_id()), desktop.GA_ROOT)
        self._hwnd = hwnd or desktop.HWND_T(self.win.winfo_id())
        self._ulw = True
        self.surface = None
        self._img = self._draw = None
        try:
            self.surface = desktop.OverlaySurface(self._hwnd, self.W, self.H)
            self._img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
            self._draw = ImageDraw.Draw(self._img)
            if not self.surface.ok:
                self._ulw = False
        except Exception:
            applog.log_exc("OverlaySurface 创建失败:\n", *sys.exc_info())
            self._ulw = False
        if self._ulw:
            desktop.style_overlay_window(self._hwnd)
        else:
            desktop.style_desktop_widget(self._hwnd, 255)
            self._make_canvas_items()
        applog.log(f"可视化渲染路径: {'ULW' if self._ulw else '画布'}")
        self._seat_above_desktop()
        self.win.after(200, self._frame)

    # ---------- AIMP 经典布局：均匀细条、紧凑排列 ----------

    def _compute_layout(self):
        w = max(2, int(3 * self.s))
        gap = max(1, int(1 * self.s))
        usable = self.W - 2 * self.pad
        xs, x = [], self.pad
        while x + w <= self.pad + usable:
            xs.append((x, w))
            x += w + gap
        return xs or [(self.pad, w)]

    def _make_canvas_items(self):
        """画布回退路径的预建图元（hidden 态，零尺寸矩形会画成 1px 线）。"""
        if self._canvas_items_ready:
            return
        cy0 = self.H // 2
        self._items_bar, self._items_pk = [], []
        for x, w in self._layout:
            self._items_bar.append(self.canvas.create_rectangle(x, cy0, x + w, cy0,
                                                                fill="#FFFFFF", outline="", width=0,
                                                                state="hidden"))
            self._items_pk.append((
                self.canvas.create_rectangle(x, cy0, x + w, cy0, fill="#FFFFFF", outline="", width=0,
                                             state="hidden"),
                self.canvas.create_rectangle(x, cy0, x + w, cy0, fill="#FFFFFF", outline="", width=0,
                                             state="hidden")))
        self._status = self.canvas.create_text(
            self.W / 2, self.H / 2, text=self._status_text,
            font=("Segoe UI", -int(10 * self.s)), fill="#888888")
        self._canvas_items_ready = True

    # ---------- 桌面级 z-order ----------

    def _seat_above_desktop(self):
        """把 Progman 压到所有覆盖窗口（面板/控件）之下；顺带处理被最小化。
        z-order 已正确时零跨进程写操作（GetWindow 是无阻塞查询）。"""
        if desktop.user32.IsIconic(self._hwnd):
            desktop.user32.ShowWindow(self._hwnd, 4)  # SW_SHOWNOACTIVATE
        desktop.register_overlay(self._hwnd)
        desktop.seat_overlays()

    # ---------- 位置/拖动 ----------

    def _anchor_pos(self):
        """跟随壁纸排版：读渲染锚点（专辑行底部），mtime 未变时走缓存。失败返回 None。"""
        p = os.path.join(self.cfg["output_dir"], "vis_anchor.json")
        try:
            mtime = os.stat(p).st_mtime
        except OSError:
            return None, 0
        if mtime == self._anchor_cache_mtime:
            return self._anchor_cache, mtime
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            pos = (int(d["x"]), int(d["y"]))
        except (OSError, ValueError, KeyError):
            pos = None
        self._anchor_cache_mtime = mtime
        self._anchor_cache = pos
        return pos, mtime

    def _auto_pos(self):
        """自动模式：优先锚点（专辑名正下方再留一档间距，间距可调），否则右下角兜底。

        兜底位置锚主屏工作区（任务栏之上）；钳制用虚拟屏——面板拖到副屏时不被拽回主屏。
        """
        pos, _ = self._anchor_pos()
        wa_l, wa_t, wa_r, wa_b = desktop.work_area()
        _gap = self.cfg.get("vis_anchor_gap")
        gap = max(0, int(10 if _gap is None else _gap)) * int(self.s)  # 0 是合法值，不能被 or 吞掉
        if pos:
            x, y = pos[0], pos[1] + gap  # 锚点(文字块底部)与面板的间距，可调
        else:
            x, y = wa_r - self.W - int(24 * self.s), wa_b - self.H - int(14 * self.s)
        vx_l, vx_t, vx_r, vx_b = desktop.virtual_screen()
        x = max(vx_l, min(x, vx_r - self.W))
        y = max(vx_t, min(y, vx_b - self.H))
        return x, y

    def _place_initial(self):
        pos = self.cfg.get("vis_pos")
        if pos and len(pos) == 2:
            x, y = int(pos[0]), int(pos[1])
        else:
            x, y = self._auto_pos()
        self.win.geometry(f"+{x}+{y}")
        self._want = (x, y)

    def _follow_anchor(self):
        """自动模式下每秒检查锚点变化（切歌/改字号时跟随）；手动定位后不跟。

        锚点消失（关文字总开关删了 vis_anchor.json）时回退到兜底位——
        此前面板会停在旧锚点位置不动。
        """
        if self.cfg.get("vis_pos"):
            return
        pos, mtime = self._anchor_pos()
        moved = False
        if pos and mtime != getattr(self, "_anchor_mtime", 0):
            self._anchor_mtime = mtime
            moved = True
        elif pos is None and self._anchor_cache is not None:
            self._anchor_cache = None  # 锚点已消失：回兜底位
            self._anchor_mtime = 0
            moved = True
        if moved:
            x, y = self._auto_pos()
            if (x, y) != self._want:
                self._want = (x, y)
                self.win.geometry(f"+{x}+{y}")

    def _screen_pos(self):
        r = desktop.wintypes.RECT()
        desktop.user32.GetWindowRect(self._hwnd, byref(r))
        return (int(r.left), int(r.top))

    def _drag_start(self, e):
        if self.cfg.get("vis_locked"):
            return
        sx, sy = self._screen_pos()
        self._drag = (e.x_root, e.y_root, sx, sy)

    def _toggle_lock(self):
        self.cfg["vis_locked"] = bool(self._lock_var.get())
        config.save(self.cfg)

    def _drag_move(self, e):
        if not self._drag:
            return
        dxr, dyr, ox, oy = self._drag
        nx, ny = ox + e.x_root - dxr, oy + e.y_root - dyr
        self._want = (nx, ny)
        self.win.geometry(f"+{nx}+{ny}")

    def _drag_end(self, e):
        if self._drag:
            self.cfg["vis_pos"] = self._screen_pos()
            config.save(self.cfg)
        self._drag = None

    def _popup(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def hide(self):
        self.cfg["vis_hidden"] = True
        config.save(self.cfg)
        self.win.withdraw()
        self.spec.pause()  # 挂起采集：活动音频流会阻止显示器睡眠（Lively #2751 同款问题）

    def show(self):
        self.cfg["vis_hidden"] = False
        config.save(self.cfg)
        self.spec.resume()
        self.win.deiconify()
        self._seat_above_desktop()

    def shutdown(self):
        """彻底销毁面板（设置改宽高后重建用）：停频谱采集线程 + 注销覆盖层 + 释放表面 + 关窗。"""
        try:
            self.spec.stop()
        except Exception:
            pass
        try:
            desktop.unregister_overlay(self._hwnd)
        except Exception:
            pass
        try:
            if self.surface is not None:
                self.surface.close()  # 不释放的话每次重建漏一张 DIB（~2MB）+ 一个 DC
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass

    def _reset_pos(self):
        self.cfg["vis_pos"] = None
        config.save(self.cfg)
        self._anchor_mtime = 0
        self._follow_anchor()
        self._seat_above_desktop()

    def _open_settings(self):
        from .settings_gui import SettingsWindow
        SettingsWindow(self.win.master, self.cfg)

    def _quit(self):
        self.cfg["vis_pos"] = self._screen_pos()
        config.save(self.cfg)
        self.win.master.destroy()

    # ---------- 帧循环：插值 + 包络 + 双渲染路径 ----------

    def _frame(self):
        # 整帧防护：任何一帧的异常都不允许断掉 after 链——链一断面板动画就永久
        # 冻结（歌词窗 _tick 有同款防护，此前这里没有）
        t0 = time.monotonic()
        try:
            self._frame_inner(t0)
        except Exception:
            applog.log_exc("频谱帧异常:\n", *sys.exc_info())
        # 自适应节奏：本帧耗时从间隔里扣除，避免 after 漂移累积
        self.win.after(max(5, self.frame_ms - int((time.monotonic() - t0) * 1000)), self._frame)

    def _frame_inner(self, t0):
        # 刷新率（vis_fps 设置，10~60）；衰减系数按秒归一，任意刷新率手感一致
        fps = max(10, min(120, int(self.cfg.get("vis_fps", 30) or 30)))
        self.frame_ms = int(round(1000 / fps))
        frame_s = self.frame_ms / 1000.0
        bar_fall = BAR_FALL_SEC ** frame_s
        peak_fall = PEAK_MULT_SEC ** frame_s
        peak_drop = PEAK_DROP_SEC * frame_s
        if time.monotonic() - getattr(self, "_last_maint", t0 - 1.0) >= 1.0:
            self._last_maint = t0  # ~1s：z-order 校验（错位才跨进程调）+ 锚点跟随
            self._lock_var.set(bool(self.cfg.get("vis_locked")))  # 设置里改锁定后同步右键菜单
            self._seat_above_desktop()
            self._follow_anchor()
        target, prev_t, t_prev, t_curr = self.spec.interp_snapshot()
        if self.spec.err:
            self._set_status(f"音频采集失败：{self.spec.err[:48]}")
            return
        self._set_status(None)

        # 时间插值：数据 ~47Hz 与显示 30fps 节拍不同，帧间线性插值让运动连续
        now = time.monotonic()
        span = max(t_curr - t_prev, 1e-3)
        alpha = max(0.0, min(1.0, (now - t_prev) / span))
        smooth = prev_t[:self.n_bands] + (target[:self.n_bands] - prev_t[:self.n_bands]) * alpha
        self._disp = np.maximum(smooth, self._disp * bar_fall)

        # 静默帧跳过：条形完全衰减后（无声音/暂停），跳过绘制与上屏——
        # 此前 30fps 一直重绘全透明帧白烧 CPU；恢复有声立刻恢复逐帧
        idle = (float(self._disp.max()) <= 0.003
                and float(self._peaks.max()) <= 0.003 and not self._status_text)
        if idle and getattr(self, "_was_idle", False):
            return
        self._was_idle = idle

        cy = self.H // 2
        ymax = (self.H // 2) - self.pad - int(2 * self.s)
        dot_h = max(1, int(self.s))

        if self._ulw:
            if not self._render_ulw(cy, ymax, dot_h, peak_fall, peak_drop):
                self._ulw = False
                applog.log("ULW 不可用，回退画布渲染")
                desktop.set_colorkey_attr(self._hwnd)
                self._geom[:] = 0
                self._make_canvas_items()
        else:
            self._render_canvas(cy, ymax, dot_h, peak_fall, peak_drop)

    def _set_status(self, text: str | None):
        """状态文字（None=清除）。"""
        if self._status_text == text:
            return
        self._status_text = text or ""
        if self._canvas_items_ready:
            self.canvas.itemconfig(self._status, text=self._status_text)

    def _render_ulw(self, cy: int, ymax: int, dot_h: int, peak_fall: float, peak_drop: float) -> bool:
        d = self._draw
        d.rectangle((0, 0, self.W, self.H), fill=(0, 0, 0, 0))
        if self._status_text:
            d.text((self.W / 2, self.H / 2), self._status_text, font=self._status_font,
                   fill=(150, 150, 150, 220), anchor="mm")
        for i, (x, w) in enumerate(self._layout):
            h = int(min(1.0, max(0.0, float(self._disp[i]))) * ymax)
            self._peaks[i] = max(self._peaks[i] * peak_fall - peak_drop, h / max(1, ymax))
            pi = int(self._peaks[i] * ymax)
            if h >= 1:  # 中轴对称：向上向下各伸展 h
                d.rectangle((x, cy - h, x + w - 1, cy + h - 1), fill=_BAR)
            if pi >= 1:  # 点状峰值帽；无声列不画（整列透明=不可见+可穿透）
                d.rectangle((x, cy - pi - dot_h, x + w - 1, cy - pi), fill=_PEAK)
                d.rectangle((x, cy + pi, x + w - 1, cy + pi + dot_h), fill=_PEAK)
        pos = self._screen_pos()
        return self.surface.update(self._img, pos=pos)

    def _render_canvas(self, cy: int, ymax: int, dot_h: int, peak_fall: float, peak_drop: float):
        self._make_canvas_items()
        c = self.canvas
        geom = self._geom
        for i, (x, w) in enumerate(self._layout):
            h = int(min(1.0, max(0.0, float(self._disp[i]))) * ymax)
            self._peaks[i] = max(self._peaks[i] * peak_fall - peak_drop, h / max(1, ymax))
            pi = int(self._peaks[i] * ymax)
            if h >= 1:
                if geom[i, 0] <= 0:
                    c.itemconfig(self._items_bar[i], state="normal")
                    geom[i, 0] = h
                    c.coords(self._items_bar[i], x, cy - h, x + w, cy + h)
                elif geom[i, 0] != h:
                    geom[i, 0] = h
                    c.coords(self._items_bar[i], x, cy - h, x + w, cy + h)
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
                elif geom[i, 1] != pi:
                    geom[i, 1] = pi
                    c.coords(self._items_pk[i][0], x, cy - pi - dot_h, x + w, cy - pi)
                    c.coords(self._items_pk[i][1], x, cy + pi, x + w, cy + pi + dot_h)
            elif geom[i, 1] > 0:
                geom[i, 1] = 0
                c.itemconfig(self._items_pk[i][0], state="hidden")
                c.itemconfig(self._items_pk[i][1], state="hidden")
