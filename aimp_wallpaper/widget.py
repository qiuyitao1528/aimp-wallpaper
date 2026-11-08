"""桌面音乐控件小部件：tkinter 单画布卡片，钉在桌面层（图标之下、壁纸之上）。

钉层用 desktop.py（Lively 同款 Progman/WorkerW 技巧，Win11 26300 适配）。
"""
from __future__ import annotations

import io
import tkinter as tk
from ctypes import byref

from PIL import Image, ImageDraw, ImageTk

from . import config, desktop
from .aimp_api import STATE_PLAYING

_GLYPHS = {"prev": "⏮", "play": "▶", "pause": "⏸", "next": "⏭"}


def _format_ms(ms) -> str:
    s = max(0, int(ms // 1000))
    return f"{s // 60}:{s % 60:02d}"


class Widget:
    def __init__(self, root: tk.Tk, ipc, cfg: dict, show_vis=None):
        self.root = root
        self.ipc = ipc
        self.cfg = cfg
        self._show_vis_cb = show_vis
        dpi = desktop.user32.GetDpiForSystem() or 96
        self.s = dpi / 96.0
        self.W = int(cfg["widget_width"] * self.s)
        self.H = int(88 * self.s)

        self.root.overrideredirect(True)
        self.root.resizable(False, False)
        self.canvas = tk.Canvas(self.root, width=self.W, height=self.H,
                                bg=desktop.KEY_HEX, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self._thumb_gen = -1
        self._thumb_img = None
        self._bg_img = None
        self._shown_title = None
        self._shown_artist = None
        self._shown_state = None
        self._drag = None
        self._bar_ratio = None
        self._menu = self._build_menu()

        self._draw_static()
        self._place_initial()
        self.root.update_idletasks()
        hwnd = desktop.user32.GetAncestor(desktop.HWND_T(self.root.winfo_id()), desktop.GA_ROOT)
        self._hwnd = hwnd or desktop.HWND_T(self.root.winfo_id())
        desktop.style_desktop_widget(self._hwnd, self.cfg.get("widget_alpha", 232))
        desktop.pin_to_desktop(self._hwnd, *self._want, self.W, self.H)
        self.root.after(500, self._tick)

    # ---------- UI ----------

    def _scaled_font(self, size_logical, bold=False):
        fam = "Segoe UI Semibold" if bold else "Segoe UI"
        return (fam, -int(size_logical * self.s))

    def _draw_static(self):
        c = self.canvas
        W, H, s = self.W, self.H, self.s
        bg = Image.new("RGB", (W, H), desktop.KEY)
        d = ImageDraw.Draw(bg)
        r = int(14 * s)
        d.rounded_rectangle([1, 1, W - 2, H - 2], radius=r, fill=(24, 26, 34))
        d.rounded_rectangle([1, 1, W - 2, H - 2], radius=r, outline=(60, 64, 80), width=1)
        self._bg_img = ImageTk.PhotoImage(bg)
        c.create_image(0, 0, image=self._bg_img, anchor="nw", tags=("bg",))

        pad = int(14 * s)
        self.thumb_size = int(56 * s)
        c.create_rectangle(pad, (H - self.thumb_size) // 2, pad + self.thumb_size,
                           (H + self.thumb_size) // 2, outline="", tags=("thumbbox",))
        self.tx = pad + self.thumb_size + int(12 * s)
        bx = W - int(26 * s)
        c.create_text(bx - int(84 * s), int(30 * s), text=_GLYPHS["prev"],
                      font=("Segoe UI Symbol", -int(12 * self.s)), fill="#AEB5C4", tags=("btn_prev",))
        c.create_text(bx - int(42 * s), int(29 * s), text=_GLYPHS["play"],
                      font=("Segoe UI Symbol", -int(16 * self.s)), fill="#E8EAF0", tags=("btn_play",))
        c.create_text(bx, int(30 * s), text=_GLYPHS["next"],
                      font=("Segoe UI Symbol", -int(12 * self.s)), fill="#AEB5C4", tags=("btn_next",))
        c.tag_bind("btn_prev", "<Button-1>", lambda e: self.ipc.prev())
        c.tag_bind("btn_next", "<Button-1>", lambda e: self.ipc.next())
        c.tag_bind("btn_play", "<Button-1>", lambda e: self.ipc.playpause())

        # 进度条（背景槽 + 填充条），点击/拖动跳转
        self.bar_x0 = self.tx
        self.bar_x1 = W - int(112 * s)
        self.bar_y = int(68 * s)
        self.bar_h = int(5 * s)
        c.create_rectangle(self.bar_x0, self.bar_y, self.bar_x1, self.bar_y + self.bar_h,
                           fill="#33384A", outline="", tags=("bar",))
        self.bar_fill = c.create_rectangle(self.bar_x0, self.bar_y, self.bar_x0, self.bar_y + self.bar_h,
                                           fill="#D9DEEA", outline="", tags=("barfill",))
        self.time_text = c.create_text(self.bar_x1 + int(10 * s), self.bar_y + self.bar_h // 2,
                                       text="0:00 / 0:00", anchor="w",
                                       font=self._scaled_font(9), fill="#8A92A6")
        c.tag_bind("bar", "<Button-1>", self._bar_press)
        c.tag_bind("bar", "<B1-Motion>", self._bar_press)
        c.tag_bind("bar", "<ButtonRelease-1>", self._bar_release)

        # 可拖拽区域（标题/歌手文本 + 背景空白处）
        self.title_item = c.create_text(self.tx, int(20 * s), text="", anchor="w", width=self.bar_x1 - self.tx,
                                        font=self._scaled_font(12, bold=True), fill="#F2F4F8")
        self.artist_item = c.create_text(self.tx, int(41 * s), text="", anchor="w", width=self.bar_x1 - self.tx,
                                         font=self._scaled_font(10), fill="#A9B1C2")
        for tag in ("bg", "thumbbox"):
            c.tag_bind(tag, "<Button-1>", self._drag_start)
            c.tag_bind(tag, "<B1-Motion>", self._drag_move)
            c.tag_bind(tag, "<ButtonRelease-1>", self._drag_end)
        c.tag_bind("bg", "<Button-3>", self._popup_menu)

    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        if self._show_vis_cb:
            m.add_command(label="显示可视化面板", command=self._show_vis_cb)
        m.add_command(label="恢复原壁纸", command=self._restore)
        m.add_separator()
        m.add_command(label="退出", command=self._quit)
        return m

    def _popup_menu(self, e):
        try:
            self._menu.tk_popup(e.x_root, e.y_root)
        finally:
            self._menu.grab_release()

    def _restore(self):
        from . import wallpaper
        msg = wallpaper.restore_original(self.cfg)
        self.canvas.itemconfig(self.title_item, text=msg, fill="#F2C46B")
        self.root.after(3000, lambda: setattr(self, "_shown_title", None))

    def _quit(self):
        try:
            self.cfg["widget_pos"] = self._screen_pos()
            config.save(self.cfg)
        except Exception:
            pass  # 存位置失败绝不拦退出
        self.root.destroy()

    # ---------- 位置 ----------

    def _place_initial(self):
        pos = self.cfg.get("widget_pos")
        if pos and len(pos) == 2:
            x, y = int(pos[0]), int(pos[1])
        else:
            wa_l, wa_t, wa_r, wa_b = desktop.work_area()
            x = wa_l + (wa_r - wa_l - self.W) // 2
            y = wa_b - self.H - int(10 * self.s)
        self.root.geometry(f"+{x}+{y}")
        self._want = (x, y)

    def _screen_pos(self) -> tuple[int, int]:
        r = desktop.wintypes.RECT()
        desktop.user32.GetWindowRect(desktop.HWND_T(self._hwnd), byref(r))
        return (int(r.left), int(r.top))

    def _drag_start(self, e):
        self._drag = (e.x, e.y, *self._screen_pos())

    def _drag_move(self, e):
        if not self._drag:
            return
        dx, dy, ox, oy = self._drag
        parent = desktop.user32.GetParent(desktop.HWND_T(self._hwnd))
        pr = desktop.wintypes.RECT()
        if parent:
            desktop.user32.GetWindowRect(parent, byref(pr))
        nx = ox + e.x - dx - pr.left
        ny = oy + e.y - dy - pr.top
        self._want = (ox + e.x - dx, oy + e.y - dy)
        desktop.user32.MoveWindow(desktop.HWND_T(self._hwnd), nx, ny, self.W, self.H, True)

    def _drag_end(self, e):
        if self._drag:
            self.cfg["widget_pos"] = self._screen_pos()
            config.save(self.cfg)
        self._drag = None

    # ---------- 进度条 ----------

    def _bar_press(self, e):
        ratio = (e.x - self.bar_x0) / max(1, self.bar_x1 - self.bar_x0)
        self._bar_ratio = max(0.0, min(1.0, ratio))
        self._paint_bar(self._bar_ratio, self._dur_now())

    def _bar_release(self, e):
        if self._bar_ratio is None:
            return
        snap = self.ipc.snapshot()
        dur = snap["duration_ms"]
        if dur > 0 and snap["connected"]:
            self.ipc.set_position(self._bar_ratio * dur)
        self._bar_ratio = None

    def _dur_now(self) -> int:
        return self.ipc.snapshot()["duration_ms"]

    def _paint_bar(self, ratio, dur_ms):
        self.canvas.coords(self.bar_fill, self.bar_x0, self.bar_y,
                           self.bar_x0 + (self.bar_x1 - self.bar_x0) * ratio, self.bar_y + self.bar_h)
        self.canvas.itemconfig(self.time_text,
                               text=f"{_format_ms(ratio * dur_ms)} / {_format_ms(dur_ms)}")

    # ---------- 周期刷新 ----------

    def _tick(self):
        snap = self.ipc.snapshot()
        connected = snap["connected"]
        title = snap["title"] if connected else "AIMP 未运行"
        artist = snap["artist"] if connected else "启动 AIMP 后自动跟随"
        if title != self._shown_title:
            self.canvas.itemconfig(self.title_item, text=title or "未知曲目",
                                   fill="#F2F4F8" if connected else "#C9CFDC")
            self._shown_title = title
        if artist != self._shown_artist:
            sub = artist
            if connected and snap["album"] and snap["album"] != artist:
                sub = f"{artist} — {snap['album']}"
            self.canvas.itemconfig(self.artist_item, text=sub or " ")
            self._shown_artist = artist

        state = snap["state"]
        if state != self._shown_state:
            glyph = _GLYPHS["pause"] if state == STATE_PLAYING else _GLYPHS["play"]
            self.canvas.itemconfig("btn_play", text=glyph)
            self._shown_state = state

        pos, dur = snap["position_ms"], snap["duration_ms"]
        if self._bar_ratio is None:
            self._paint_bar(pos / dur if dur > 0 else 0.0, dur)

        self._update_thumb(snap)
        self.root.after(500, self._tick)

    def _update_thumb(self, snap):
        gen = snap["cover_gen"]
        if gen == self._thumb_gen:
            return
        data = self.ipc.cover_now(gen)
        if data is None:
            return  # 还没就绪，下个 tick 再试（就绪=有字节或确认无封面）
        self._thumb_gen = gen
        if not data:
            img = Image.new("RGB", (self.thumb_size, self.thumb_size), (40, 44, 58))
        else:
            try:
                img = Image.open(io.BytesIO(data)).convert("RGB")
            except OSError:
                img = Image.new("RGB", (self.thumb_size, self.thumb_size), (40, 44, 58))
        img = img.resize((self.thumb_size, self.thumb_size), Image.LANCZOS)
        r = int(8 * self.s)
        mask = Image.new("L", (self.thumb_size, self.thumb_size), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, self.thumb_size - 1, self.thumb_size - 1],
                                               radius=r, fill=255)
        img.putalpha(mask)
        self._thumb_img = ImageTk.PhotoImage(img)
        box = self.canvas.coords("thumbbox")
        self.canvas.delete("thumbimg")
        self.canvas.create_image(box[0], box[1], image=self._thumb_img, anchor="nw", tags=("thumbimg",))
        self.canvas.tag_bind("thumbimg", "<Button-1>", self._drag_start)
        self.canvas.tag_bind("thumbimg", "<B1-Motion>", self._drag_move)
        self.canvas.tag_bind("thumbimg", "<ButtonRelease-1>", self._drag_end)
