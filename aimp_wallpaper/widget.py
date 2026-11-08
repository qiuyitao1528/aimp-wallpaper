"""桌面音乐控件：ULW 半透明圆角卡片（封面缩略图/播放控制/进度条）。

渲染走 UpdateLayeredWindow 逐像素 alpha（同频谱面板）：PIL 画帧 → 预乘 BGRA →
原子呈现；Tk 仅作窗口壳与事件源。可见性自管理：_tick 检查 cfg["widget_hidden"]，
托盘/设置改配置 500ms 内生效，无需重启。
"""
from __future__ import annotations

import io
import time
import tkinter as tk
from ctypes import byref

from PIL import Image, ImageDraw

from . import config, desktop, wallpaper
from .aimp_api import STATE_PLAYING

_GLYPHS = {"prev": "⏮", "play": "▶", "pause": "⏸", "next": "⏭"}
_CARD = (22, 24, 32)
_CARD_LINE = (62, 66, 84)
_TXT_MAIN = (242, 244, 248, 255)
_TXT_SUB = (169, 177, 194, 255)
_TXT_DIM = (138, 146, 166, 255)
_BTN = (174, 181, 196, 255)
_BTN_HOVER = (255, 255, 255, 255)
_BTN_BG = (52, 58, 76, 200)
_BAR_TRACK = (51, 56, 74, 210)
_BAR_FILL = (217, 222, 234, 255)


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
        self.a = max(60, min(255, int(cfg.get("widget_alpha", 232))))

        self.root.overrideredirect(True)
        self.root.resizable(False, False)
        self.root.configure(bg=desktop.KEY_HEX)

        self._img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        self._draw = ImageDraw.Draw(self._img)
        self._thumb = None
        self._thumb_gen = -1
        self._shown_title = None
        self._shown_artist = None
        self._playing = False
        self._bar_shown = 0.0
        self._dur_cache = 0
        self._bar_ratio = None      # 拖动进度条时的临时 ratio
        self._hover = None
        self._drag = None
        self._seeking = False
        self._msg = None
        self._msg_until = 0.0
        self._is_hidden = bool(cfg.get("widget_hidden"))

        self._menu = self._build_menu()
        self._place_initial()
        self._layout_metrics()
        self._render()

        self.root.update_idletasks()
        hwnd = desktop.user32.GetAncestor(desktop.HWND_T(self.root.winfo_id()), desktop.GA_ROOT)
        self._hwnd = hwnd or desktop.HWND_T(self.root.winfo_id())
        desktop.register_overlay(self._hwnd)
        desktop.style_overlay_window(self._hwnd)
        self.surface = desktop.OverlaySurface(self._hwnd, self.W, self.H)
        desktop.seat_overlays()
        self._render()  # surface 就绪后呈现首帧

        for seq, fn in (("<Button-1>", self._on_click), ("<B1-Motion>", self._on_motion),
                        ("<ButtonRelease-1>", self._on_release), ("<Motion>", self._on_hover),
                        ("<Button-3>", self._popup_menu)):
            self.root.bind(seq, fn)
        self.root.after(500, self._tick)
        if self._is_hidden:
            self.root.withdraw()

    # ---------- 布局与命中 ----------

    def _layout_metrics(self):
        s = self.s
        self.pad = int(14 * s)
        self.thumb_size = int(56 * s)
        self.tx = self.pad + self.thumb_size + int(12 * s)
        self.bx = self.W - int(26 * s)
        self.bar_x0 = self.tx
        self.bar_x1 = self.W - int(112 * s)
        self.bar_y = int(68 * s)
        self.bar_h = int(5 * s)
        self.btn_cy = int(30 * s)
        br = int(13 * s)
        self.buttons = [
            {"name": "prev", "cx": self.bx - int(84 * s), "cy": self.btn_cy,
             "rect": (self.bx - int(96 * s), self.btn_cy - br, self.bx - int(72 * s), self.btn_cy + br),
             "font": wallpaper._load_font(False, int(12 * s), "segoeuisym.ttf")[0]},
            {"name": "play", "cx": self.bx - int(42 * s), "cy": self.btn_cy,
             "rect": (self.bx - int(58 * s), self.btn_cy - br, self.bx - int(26 * s), self.btn_cy + br),
             "font": wallpaper._load_font(False, int(17 * s), "segoeuisym.ttf")[0]},
            {"name": "next", "cx": self.bx, "cy": self.btn_cy,
             "rect": (self.bx - int(12 * s), self.btn_cy - br, self.bx + int(12 * s), self.btn_cy + br),
             "font": wallpaper._load_font(False, int(12 * s), "segoeuisym.ttf")[0]},
        ]
        self.font_title = wallpaper._load_font(True, int(12 * s) + 2, "segoeuisb.ttf")[0]
        self.font_artist = wallpaper._load_font(False, int(10 * s) + 1, "segoeui.ttf")[0]
        self.font_time = wallpaper._load_font(False, int(9 * s) + 1, "segoeui.ttf")[0]

    def _hit(self, x, y):
        for b in self.buttons:
            x0, y0, x1, y1 = b["rect"]
            if x0 <= x <= x1 and y0 <= y <= y1:
                return ("btn", b["name"])
        if self.bar_x0 - 4 <= x <= self.bar_x1 + 4 and self.bar_y - 6 <= y <= self.bar_y + self.bar_h + 6:
            return ("bar", None)
        return ("card", None)

    # ---------- 绘制 ----------

    def _title_text(self):
        if self._msg:
            return self._msg
        t = self._shown_title or "未知曲目"
        return wallpaper._ellipsis(self._draw, t, self.font_title, self.bar_x1 - self.tx)

    def _artist_text(self):
        a = self._shown_artist or " "
        return wallpaper._ellipsis(self._draw, a, self.font_artist, self.bar_x1 - self.tx)

    def _render(self):
        img, d = self._img, self._draw
        s = self.s
        d.rectangle((0, 0, self.W, self.H), fill=(0, 0, 0, 0))
        d.rounded_rectangle((1, 1, self.W - 2, self.H - 2), radius=int(16 * s),
                            fill=_CARD + (self.a,), outline=_CARD_LINE + (140,), width=1)
        if self._thumb is not None:
            img.paste(self._thumb, (self.pad, (self.H - self.thumb_size) // 2), self._thumb)
        d.text((self.tx, int(15 * s)), self._title_text(), font=self.font_title, fill=_TXT_MAIN)
        d.text((self.tx, int(37 * s)), self._artist_text(), font=self.font_artist, fill=_TXT_SUB)
        for b in self.buttons:
            if self._hover == b["name"]:
                d.ellipse((b["cx"] - int(15 * s), b["cy"] - int(15 * s),
                           b["cx"] + int(15 * s), b["cy"] + int(15 * s)), fill=_BTN_BG)
            glyph = _GLYPHS["pause"] if (b["name"] == "play" and self._playing) else _GLYPHS[b["name"]]
            col = _BTN_HOVER if self._hover == b["name"] else _BTN
            d.text((b["cx"], b["cy"] + int(1 * s)), glyph, font=b["font"], fill=col, anchor="mm")
        ratio = self._bar_ratio if self._bar_ratio is not None else self._bar_shown
        d.rounded_rectangle((self.bar_x0, self.bar_y, self.bar_x1, self.bar_y + self.bar_h),
                            radius=self.bar_h // 2, fill=_BAR_TRACK)
        fill_w = int((self.bar_x1 - self.bar_x0) * ratio)
        if fill_w > self.bar_h:
            d.rounded_rectangle((self.bar_x0, self.bar_y, self.bar_x0 + fill_w, self.bar_y + self.bar_h),
                                radius=self.bar_h // 2, fill=_BAR_FILL)
        d.text((self.bar_x1 + int(10 * s), self.bar_y + self.bar_h // 2),
               f"{_format_ms(ratio * self._dur_cache)} / {_format_ms(self._dur_cache)}",
               font=self.font_time, fill=_TXT_DIM, anchor="lm")
        surf = getattr(self, "surface", None)  # __init__ 早期 surface 尚未创建
        if surf is not None:
            surf.update(self._img, pos=self._screen_pos())

    # ---------- 事件 ----------

    def _on_click(self, e):
        kind, name = self._hit(e.x, e.y)
        if kind == "btn":
            if name == "prev":
                self.ipc.prev()
            elif name == "next":
                self.ipc.next()
            else:
                self.ipc.playpause()
        elif kind == "bar":
            self._seeking = True
            self._bar_press(e)

    def _on_motion(self, e):
        if self._seeking:
            self._bar_press(e)
        elif self._drag:
            dx, dy, ox, oy = self._drag
            nx, ny = ox + e.x - dx, oy + e.y - dy
            self._want = (nx, ny)
            self.root.geometry(f"+{nx}+{ny}")

    def _on_release(self, e):
        if self._seeking:
            self._seeking = False
            snap = self.ipc.snapshot()
            if snap["duration_ms"] > 0 and snap["connected"]:
                self.ipc.set_position(self._bar_ratio * snap["duration_ms"])
            self._bar_ratio = None
            self._render()
        elif self._drag:
            self._drag_end(e)

    def _on_hover(self, e):
        if self._drag or self._seeking:
            return
        kind, name = self._hit(e.x, e.y)
        hover = name if kind == "btn" else None
        if hover != self._hover:
            self._hover = hover
            self._render()

    def _bar_press(self, e):
        ratio = (e.x - self.bar_x0) / max(1, self.bar_x1 - self.bar_x0)
        self._bar_ratio = max(0.0, min(1.0, ratio))
        self._render()

    def _popup_menu(self, e):
        try:
            self._menu.tk_popup(e.x_root, e.y_root)
        finally:
            try:
                self._menu.grab_release()
            except Exception:
                pass

    # ---------- 菜单动作 ----------

    def _restore(self):
        from . import wallpaper
        self._msg = wallpaper.restore_original(self.cfg)
        self._msg_until = time.monotonic() + 3.0
        self._shown_title = None
        self._render()

    def _quit(self):
        try:
            self.cfg["widget_pos"] = self._screen_pos()
            config.save(self.cfg)
        except Exception:
            pass  # 存位置失败绝不拦退出
        self.root.destroy()

    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        if self._show_vis_cb:
            m.add_command(label="显示 / 隐藏频谱面板", command=self._show_vis_cb)
        m.add_command(label="恢复原壁纸", command=self._restore)
        m.add_command(label="设置…", command=self._open_settings)
        m.add_separator()
        m.add_command(label="隐藏控件", command=self._hide_self)
        m.add_command(label="退出", command=self._quit)
        return m

    def _open_settings(self):
        from .settings_gui import SettingsWindow
        SettingsWindow(self.root, self.cfg)

    def _hide_self(self):
        self.cfg["widget_hidden"] = True
        config.save(self.cfg)

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

    def _drag_end(self, e):
        if self._drag:
            self.cfg["widget_pos"] = self._screen_pos()
            config.save(self.cfg)
        self._drag = None

    # ---------- 周期刷新 ----------

    def _tick(self):
        snap = self.ipc.snapshot()
        hidden = bool(self.cfg.get("widget_hidden"))
        if hidden != self._is_hidden:
            self._is_hidden = hidden
            (self.root.withdraw if hidden else self.root.deiconify)()
            if not hidden:
                desktop.seat_overlays()
        if hidden:
            self.root.after(500, self._tick)
            return

        changed = []
        title = snap["title"] if snap["connected"] else "AIMP 未运行"
        artist = snap["artist"] if snap["connected"] else "启动 AIMP 后自动跟随"
        if snap["connected"] and snap["album"] and snap["album"] != artist:
            artist = f"{artist} — {snap['album']}"
        if title != self._shown_title:
            self._shown_title = title
            changed.append("title")
        if artist != self._shown_artist:
            self._shown_artist = artist
            changed.append("artist")
        playing = snap["state"] == STATE_PLAYING
        if playing != self._playing:
            self._playing = playing
            changed.append("state")
        dur = snap["duration_ms"]
        ratio = snap["position_ms"] / dur if dur > 0 else 0.0
        if self._bar_ratio is None and (abs(ratio - self._bar_shown) > 0.002 or dur != self._dur_cache):
            self._bar_shown = ratio
            self._dur_cache = dur
            changed.append("bar")
        if self._msg and time.monotonic() > self._msg_until:
            self._msg = None
            self._shown_title = None
            changed.append("msg")
        self._update_thumb(snap, changed)
        if changed:
            self._render()
        self.root.after(500, self._tick)

    def _update_thumb(self, snap, changed):
        gen = snap["cover_gen"]
        if gen == self._thumb_gen:
            return
        data = self.ipc.cover_now(gen)
        if data is None:
            return  # 还没就绪，下个 tick 再试（就绪=有字节或确认无封面）
        self._thumb_gen = gen
        if data:
            try:
                img = Image.open(io.BytesIO(data)).convert("RGB")
            except OSError:
                img = Image.new("RGB", (self.thumb_size,) * 2, (40, 44, 58))
        else:
            img = Image.new("RGB", (self.thumb_size,) * 2, (40, 44, 58))
        img = img.resize((self.thumb_size, self.thumb_size), Image.LANCZOS)
        mask = Image.new("L", (self.thumb_size, self.thumb_size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, self.thumb_size - 1, self.thumb_size - 1),
                                               radius=int(8 * self.s), fill=255)
        img.putalpha(mask)
        self._thumb = img
        changed.append("thumb")
