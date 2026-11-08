"""可视化面板：桌面右下角实时频谱，100% 复原 AIMP 经典样式——

- 背景完全透明（色键分层，壁纸直接透出）
- 条形以水平中轴上下对称
- 条宽从左（低频）到右（高频）由粗变细
- 白色细条 + 点状峰值帽

渲染路线（Win11 26300 实测可行）：保持顶层窗口不 SetParent，色键分层
（矩阵实验 m4 验证可绘制），SetWindowPos 把 Progman 压到本窗口下方得到
桌面级 z-order，最小化自愈。
"""
from __future__ import annotations

import tkinter as tk
from ctypes import byref

import numpy as np

from . import config, desktop
from .audio_spectrum import Spectrum

_BAR = "#FFFFFF"
_PEAK = "#FFFFFF"


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
        self.canvas = tk.Canvas(self.win, width=self.W, height=self.H,
                                bg=desktop.KEY_HEX, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)
        self.canvas.bind("<Button-3>", self._popup)

        self.menu = tk.Menu(self.win, tearoff=0)
        self.menu.add_command(label="设置…", command=self._open_settings)
        self.menu.add_command(label="跟随壁纸位置", command=self._reset_pos)
        self._lock_var = tk.BooleanVar(value=bool(self.cfg.get("vis_locked")))
        self.menu.add_checkbutton(label="锁定（禁拖动）", variable=self._lock_var,
                                  command=self._toggle_lock)
        self.menu.add_separator()
        self.menu.add_command(label="隐藏面板", command=self.hide)
        self.menu.add_command(label="退出", command=self._quit)

        self._layout = self._compute_layout()  # [(x, w), ...]
        self.n_bands = len(self._layout)
        self._status = self.canvas.create_text(self.W / 2, self.H / 2, text="正在接入系统声音…",
                                               font=("Segoe UI", -int(10 * self.s)), fill="#888888")
        self._status_shown = "boot"
        # 预建画布元素，每帧只改 coords（Tk 建元素开销大，delete+重建是卡顿主因）
        cy0 = self.H // 2
        self._items_bar, self._items_pk = [], []
        for x, w in self._layout:
            self._items_bar.append(self.canvas.create_rectangle(x, cy0, x + w, cy0,
                                                                fill=_BAR, outline="", width=0))
            self._items_pk.append((
                self.canvas.create_rectangle(x, cy0, x + w, cy0, fill=_PEAK, outline="", width=0),
                self.canvas.create_rectangle(x, cy0, x + w, cy0, fill=_PEAK, outline="", width=0)))
        self._disp = np.zeros(self.n_bands)          # UI 层包络值
        self._peaks = np.zeros(self.n_bands)
        self._geom = np.zeros((self.n_bands, 2), dtype=int)  # [h, p] 整数缓存，未变不重绘
        self._drag = None
        self._tick_n = 0

        self.spec = Spectrum(n_bands=self.n_bands, f_max=cfg.get("vis_fmax", 16000))
        self.spec.start()

        self._place_initial()
        self.win.update_idletasks()
        hwnd = desktop.user32.GetAncestor(desktop.HWND_T(self.win.winfo_id()), desktop.GA_ROOT)
        self._hwnd = hwnd or desktop.HWND_T(self.win.winfo_id())
        # 色键分层：KEY 色像素全透明（壁纸透出），其余不透明；矩阵实验 m4 验证可绘制
        desktop.style_desktop_widget(self._hwnd, 255)
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

    # ---------- 桌面级 z-order ----------

    def _seat_above_desktop(self):
        """把 Progman 压到本窗口之下（壁纸之上、普通窗口之下）；顺带处理被最小化。"""
        if desktop.user32.IsIconic(self._hwnd):
            desktop.user32.ShowWindow(self._hwnd, 4)  # SW_SHOWNOACTIVATE
        progman = desktop.user32.FindWindowW("Progman", None)
        if progman:
            desktop.user32.SetWindowPos(progman, self._hwnd, 0, 0, 0, 0,
                                        0x2 | 0x1 | 0x10)  # NOMOVE|NOSIZE|NOACTIVATE

    # ---------- 位置/拖动 ----------

    def _anchor_pos(self):
        """跟随壁纸排版：读渲染锚点（专辑行底部），失败返回 None。"""
        import json
        import os
        p = os.path.join(self.cfg["output_dir"], "vis_anchor.json")
        try:
            st = os.stat(p)
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            return (int(d["x"]), int(d["y"])), st.st_mtime
        except (OSError, ValueError, KeyError):
            return None, 0

    def _auto_pos(self):
        """自动模式：优先锚点（专辑名正下方再留一档间距），否则右下角兜底。"""
        pos, _ = self._anchor_pos()
        wa_l, wa_t, wa_r, wa_b = desktop.work_area()
        if pos:
            x, y = pos[0], pos[1] + int(10 * self.s)  # 锚点(专辑行下 13px)再往下挪一档
        else:
            x, y = wa_r - self.W - int(24 * self.s), wa_b - self.H - int(14 * self.s)
        x = max(wa_l, min(x, wa_r - self.W))
        y = max(wa_t, min(y, wa_b - self.H))
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
        """自动模式下每秒检查锚点变化（切歌/改字号时跟随）；手动定位后不跟。"""
        if self.cfg.get("vis_pos"):
            return
        pos, mtime = self._anchor_pos()
        if pos and mtime != getattr(self, "_anchor_mtime", 0):
            self._anchor_mtime = mtime
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

    def show(self):
        self.cfg["vis_hidden"] = False
        config.save(self.cfg)
        self.win.deiconify()
        self._seat_above_desktop()

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
        try:
            self.cfg["vis_pos"] = self._screen_pos()
            config.save(self.cfg)
        except Exception:
            pass  # 存位置失败绝不拦退出
        self.win.master.destroy()

    # ---------- 绘制循环：均匀条 + 中轴对称 + 点状峰值 ----------

    def _frame(self):
        self._tick_n += 1
        if self._tick_n % 60 == 1:  # ~1s：z-order 强化 + 最小化自愈 + 锚点跟随
            self._seat_above_desktop()
            self._follow_anchor()
        c = self.canvas
        target = self.spec.snapshot()
        if self.spec.err:
            if self._status_shown != "err":
                self._status_shown = "err"
                c.itemconfig(self._status, text=f"音频采集失败：{self.spec.err[:48]}")
            c.after(1000, self._frame)
            return
        if self._status_shown:
            self._status_shown = ""
            c.itemconfig(self._status, text="")
        # 攻/衰包络在 UI 层按帧率做：立即攻、指数衰（60fps 平滑，替代音频线程 23Hz 步进）
        self._disp = np.maximum(target[:self.n_bands], self._disp * 0.93)
        cy = self.H // 2
        ymax = (self.H // 2) - self.pad - int(2 * self.s)
        dot_h = max(1, int(self.s))
        geom = self._geom
        for i, (x, w) in enumerate(self._layout):
            h = int(min(1.0, max(0.0, float(self._disp[i]))) * ymax)
            self._peaks[i] = max(self._peaks[i] * 0.994 - 0.0006, h / max(1, ymax))
            pi = int(max(dot_h + 1, self._peaks[i] * ymax))
            if geom[i, 0] != h:  # 中轴对称：向上向下各伸展 h
                geom[i, 0] = h
                if h >= 1:
                    c.coords(self._items_bar[i], x, cy - h, x + w, cy + h)
                else:
                    c.coords(self._items_bar[i], x, cy, x + w, cy)
            if geom[i, 1] != pi:  # 点状峰值帽
                geom[i, 1] = pi
                c.coords(self._items_pk[i][0], x, cy - pi - dot_h, x + w, cy - pi)
                c.coords(self._items_pk[i][1], x, cy + pi, x + w, cy + pi + dot_h)
        self.win.after(16, self._frame)
