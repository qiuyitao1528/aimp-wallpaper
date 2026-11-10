"""歌词获取与显示：来源 缓存 → 本地 .lrc → 网易云在线（参考 jitwxs/163MusicLyrics 思路）。

- LRC 解析：[mm:ss.xx] 多时间标签、[offset:±ms]、增强格式 <mm:ss.xx> 词级标签剥离
- 抓取在后台线程，结果仅替换 lines 列表（GIL 下安全）
- LyricsWindow：ULW 逐像素 alpha 覆盖窗，显示当前行+下一行，跟随频谱面板/封面锚点；
  文字样式与壁纸歌名行同源（lyrics_* 配置键，迁移时从 title_* 播种）
"""
from __future__ import annotations

import bisect
import hashlib
import json
import os
import re
import sys
import threading
import urllib.parse
import urllib.request
import tkinter as tk
from ctypes import byref

from PIL import Image, ImageDraw

from . import applog, config, desktop, wallpaper

NETEASE_SEARCH = "https://music.163.com/api/search/get?s={kw}&type=1&limit=8"
NETEASE_LYRIC = "https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://music.163.com"}
_STAMP = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_WORDTAG = re.compile(r"<\d+:\d+(?:\.\d+)?>")
_BRACKETS = re.compile(r"[（(【\[][^）)】\]]*[）)】\]]")


def _http_json(url: str, timeout: int = 6):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _stamp_ms(minute: str, sec: str, frac: str | None, offset_ms: int = 0) -> int:
    fr = int(frac or 0)
    if len(frac or "") <= 2:
        fr *= 10
    return int(minute) * 60_000 + int(sec) * 1000 + fr + offset_ms


def parse_lrc(text: str) -> list[tuple[int, str]]:
    """LRC → [(ms, 歌词)] 按 ms 排序；跳过 [ti:]/[ar:] 等元数据与空行。"""
    offset = 0
    out: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^\s*\[offset:\s*([+-]?\d+)\s*\]", line, re.I)
        if m:
            offset = int(m.group(1))
            continue
        stamps = _STAMP.findall(line)
        if not stamps:
            continue  # [ti:]/[ar:] 等元数据行
        content = _WORDTAG.sub("", _STAMP.sub("", line, count=len(stamps))).strip()
        for minute, sec, frac in stamps:
            out.append((_stamp_ms(minute, sec, frac, offset), content))
    out.sort(key=lambda e: e[0])
    return out


def _search_netease(title: str, artist: str, duration_ms: int | None) -> tuple[str | None, str | None]:
    """网易云搜索 → 选时长最接近的歌曲 → 返回 (原文 LRC, 翻译 LRC)。"""
    kws = []
    t = _BRACKETS.sub("", title).strip()
    a = _BRACKETS.sub("", artist).strip()
    if a and a != "未知艺术家":
        kws.append(f"{a} {t}")
    kws.append(t)
    for kw in kws:
        try:
            res = _http_json(NETEASE_SEARCH.format(kw=urllib.parse.quote(kw)))
            songs = (res.get("result") or {}).get("songs") or []
        except Exception:
            continue
        if not songs:
            continue
        best = songs[0]
        if duration_ms:
            near = [s for s in songs if abs(int(s.get("duration") or 0) - duration_ms) <= 5000]
            if near:
                best = near[0]
        try:
            ly = _http_json(NETEASE_LYRIC.format(sid=best["id"]))
            lrc = (ly.get("lrc") or {}).get("lyric") or ""
            if lrc.strip():
                return lrc, (ly.get("tlyric") or {}).get("lyric") or None
        except Exception:
            continue
    return None, None


def _local_lrc_candidates(audio_path: str, title: str) -> list[str]:
    cands = []
    if audio_path and os.path.isabs(audio_path):
        base = os.path.splitext(audio_path)[0]
        cands.append(base + ".lrc")
        cands.append(os.path.join(os.path.dirname(audio_path), title.strip() + ".lrc"))
    return cands


def _pair_lyrics(orig: list[tuple[int, str]], trans_lines: list[tuple[int, str]] | None = None):
    """合并原文/翻译 → [(ms, 原文, 翻译)]。

    网易云：tlyric 按时间戳精确配对；本地双语 LRC：同时间戳连续双行，第二行视为翻译。
    """
    tmap: dict[int, str] = {}
    for ms, t in (trans_lines or []):
        tmap.setdefault(ms, t)
    out: list[tuple[int, str, str]] = []
    i = 0
    while i < len(orig):
        ms, text = orig[i]
        tr = tmap.get(ms, "")
        if not tr and i + 1 < len(orig) and orig[i + 1][0] == ms:
            tr = orig[i + 1][1]
            i += 1
        out.append((ms, text, tr))
        i += 1
    return out


def fetch_lrc(title: str, artist: str, duration_ms: int | None,
              cache_dir: str, audio_path: str | None = None):
    """缓存 → 本地 .lrc → 网易云。返回 [(ms, 原文, 翻译)]（翻译可为空串），失败 None。"""
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.md5(f"{title.lower()}|{artist.lower()}".encode("utf-8")).hexdigest()
    cache_file = os.path.join(cache_dir, key + ".lrc")

    lrc_text = None
    if os.path.exists(cache_file):
        try:
            lrc_text = open(cache_file, "r", encoding="utf-8").read()
        except OSError:
            lrc_text = None
    if lrc_text is None:
        for cand in _local_lrc_candidates(audio_path or "", title):
            if os.path.exists(cand):
                for enc in ("utf-8", "gbk", "utf-16"):
                    try:
                        lrc_text = open(cand, "r", encoding=enc).read()
                        break
                    except (OSError, UnicodeDecodeError):
                        continue
                if lrc_text:
                    break
    tlyric_text = None
    if lrc_text is None:
        lrc_text, tlyric_text = _search_netease(title, artist, duration_ms)
    if not lrc_text:
        return None
    lines = parse_lrc(lrc_text)
    if lines and tlyric_text:
        lines = _pair_lyrics(lines, parse_lrc(tlyric_text))
    elif lines:
        lines = _pair_lyrics(lines)
    if lines:
        try:  # 回写规范化结果（翻译行与原文同时间戳），缓存命中路径也保留对照
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write("\n".join(
                    f"[{ms // 60000:02d}:{ms % 60000 // 1000:02d}.{ms % 1000:03d}]{t}"
                    + (f"\n[{ms // 60000:02d}:{ms % 60000 // 1000:02d}.{ms % 1000:03d}]{tr}" if tr else "")
                    for ms, t, tr in lines))
        except OSError:
            pass
    return lines or None


class LyricsFetcher(threading.Thread):
    """监视当前曲目，变更时后台抓取歌词。"""

    def __init__(self, ipc, cfg, on_lines):
        super().__init__(daemon=True, name="lyrics")
        self.ipc = ipc
        self.cfg = cfg
        self.on_lines = on_lines  # callable(lines | None)
        self._key = None
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.wait(1.0):
            try:
                snap = self.ipc.snapshot()
                if not snap["connected"] or not (snap["title"] or snap["filename"]):
                    continue
                key = (snap["title"], snap["artist"])
                if key == self._key:
                    continue
                self._key = key
                lines = fetch_lrc(snap["title"], snap["artist"], snap["duration_ms"] or None,
                                  self.cfg["output_dir"], snap.get("filename"))
                self.on_lines(lines)
            except Exception:
                applog.log_exc("歌词抓取异常:\n", *sys.exc_info())


class LyricsWindow:
    """歌词窗：ULW 原子呈现，默认跟随频谱面板下方（面板隐藏时跟随封面锚点）。"""

    def __init__(self, root: tk.Tk, ipc, cfg: dict, get_panel_pos):
        self.cfg = cfg
        self.ipc = ipc
        self.get_panel_pos = get_panel_pos  # () -> (x, y) | None（面板不可见时 None）
        self.s = (desktop.user32.GetDpiForSystem() or 96) / 96.0
        self.lines: list[tuple[int, str]] = []
        self._times: list[int] = []  # 歌词未就绪时 _tick 也要能跑（set_lines 前不存在会炸链）
        self._line_idx = -1
        self._shown_pair = None
        self._drag = None
        self._last_follow = None
        self._font_key = None
        self._font_cache = {}
        self._img = None
        self._draw = None
        self.surface = None
        self._hwnd = None

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.resizable(False, False)
        self.win.configure(bg=desktop.KEY_HEX)
        self.win.bind("<Button-1>", self._drag_start)
        self.win.bind("<B1-Motion>", self._drag_move)
        self.win.bind("<ButtonRelease-1>", self._drag_end)
        self.win.bind("<Button-3>", self._popup)

        self._menu = tk.Menu(self.win, tearoff=0)
        self._lock_var = tk.BooleanVar(value=bool(cfg.get("lyrics_locked")))
        self._menu.add_checkbutton(label="锁定（禁拖动）", variable=self._lock_var,
                                   command=self._toggle_lock)
        self._menu.add_command(label="隐藏歌词", command=self._hide_self)
        self._menu.add_command(label="设置…", command=self._open_settings)

        self._ensure_fonts()  # 字体/窗高/表面全部在这里按 cfg 建立（win 之后才能读屏幕尺寸）

        self._place_initial()
        self.win.update_idletasks()
        hwnd = desktop.user32.GetAncestor(desktop.HWND_T(self.win.winfo_id()), desktop.GA_ROOT)
        self._hwnd = hwnd or desktop.HWND_T(self.win.winfo_id())
        desktop.register_overlay(self._hwnd)
        desktop.style_overlay_window(self._hwnd)
        self.surface = desktop.OverlaySurface(self._hwnd, self.W, self.H)
        self.surface.update(self._img, pos=self._screen_pos())
        desktop.seat_overlays()
        self.win.after(500, self._tick)
        if cfg.get("lyrics_hidden"):
            self.win.withdraw()

    # ---------- 位置 ----------

    def _anchor_pos(self):
        """跟随壁纸排版：读渲染锚点（文字块底部），mtime 未变时走缓存。失败返回 None。"""
        p = os.path.join(self.cfg["output_dir"], "vis_anchor.json")
        try:
            mtime = os.stat(p).st_mtime
        except OSError:
            return None
        if mtime == getattr(self, "_anchor_mtime", 0):
            return getattr(self, "_anchor_cache", None)
        pos = None
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            pos = (int(d["x"]), int(d["y"]))
        except (OSError, ValueError, KeyError):
            pos = None
        self._anchor_mtime = mtime
        self._anchor_cache = pos
        return pos

    def _target_pos(self):
        if self.cfg.get("lyrics_pos"):
            return tuple(self.cfg["lyrics_pos"])
        mode = self.cfg.get("lyrics_follow", "panel")
        if mode == "anchor":  # 跟随壁纸文字区（即使面板隐藏也贴着文字块底部）
            pos = self._anchor_pos()
            if pos:
                return (pos[0] + int(6 * self.s), pos[1] + int(6 * self.s))
        elif mode == "fixed":  # 固定屏幕右下，不跟随
            pass
        else:  # panel：跟随频谱面板（默认）
            panel_pos = self.get_panel_pos()
            if panel_pos:
                return (panel_pos[0] + int(6 * self.s), panel_pos[1] + self.H_panel() + int(6 * self.s))
        wa_l, wa_t, wa_r, wa_b = desktop.work_area()
        return (wa_r - self.W - int(24 * self.s), wa_b - self.H - int(120 * self.s))

    def H_panel(self) -> int:
        return int(self.cfg.get("vis_height", 120) * self.s)

    def _place_initial(self):
        pos = self._target_pos()
        self.win.geometry(f"+{pos[0]}+{pos[1]}")

    def _screen_pos(self):
        r = desktop.wintypes.RECT()
        desktop.user32.GetWindowRect(self._hwnd, byref(r))
        return (int(r.left), int(r.top))

    def _follow(self):
        if self.cfg.get("lyrics_locked") or self.cfg.get("lyrics_pos"):
            return
        pos = self._target_pos()
        if pos != self._last_follow:
            self._last_follow = pos
            if pos != self._screen_pos():
                self.win.geometry(f"+{pos[0]}+{pos[1]}")
                self.surface.update(self._img, pos=pos)  # 内容随窗口一起走

    # ---------- 显隐/锁定 ----------

    def set_hidden(self, hidden: bool):
        self.cfg["lyrics_hidden"] = hidden
        config.save(self.cfg)
        (self.win.withdraw if hidden else self.win.deiconify)()
        if not hidden:
            desktop.seat_overlays()

    def _toggle_lock(self):
        self.cfg["lyrics_locked"] = bool(self._lock_var.get())
        config.save(self.cfg)

    def _hide_self(self):
        self.set_hidden(True)

    def _open_settings(self):
        from .settings_gui import SettingsWindow
        SettingsWindow(self.win.master, self.cfg)

    def _drag_start(self, e):
        if self.cfg.get("lyrics_locked"):
            return
        sx, sy = self._screen_pos()
        self._drag = (e.x_root, e.y_root, sx, sy)

    def _drag_move(self, e):
        if not self._drag:
            return
        dxr, dyr, ox, oy = self._drag
        nx, ny = ox + e.x_root - dxr, oy + e.y_root - dyr
        self.cfg["lyrics_pos"] = [nx, ny]
        self.win.geometry(f"+{nx}+{ny}")
        # ULW 内容不跟 HWND 移动：拖动时必须立即原子重呈，否则内容滞留旧位置（消失一半）
        self.surface.update(self._img, pos=(nx, ny))

    def _drag_end(self, e):
        if self._drag:
            self.cfg["lyrics_pos"] = self._screen_pos()
            config.save(self.cfg)
            self.surface.update(self._img, pos=self._screen_pos())
        self._drag = None

    def _popup(self, e):
        try:
            self._menu.tk_popup(e.x_root, e.y_root)
        finally:
            try:
                self._menu.grab_release()
            except Exception:
                pass

    # ---------- 帧循环（2Hz 文本 + 位置跟随） ----------

    def set_lines(self, lines):
        # 兼容 (ms, 原文) 与 (ms, 原文, 翻译) 两种来源
        self.lines = [tuple(e) + ("",) * (3 - len(tuple(e))) for e in (lines or [])]
        self._times = [e[0] for e in self.lines]
        self._line_idx = -1

    def _current_index(self, pos_ms: int) -> int:
        i = bisect.bisect_right(self._times, pos_ms) - 1
        return i if i >= 0 else -1

    def _load_lyr_font(self, size: int, bold: bool):
        """歌词字体带缓存（同字号/粗细/字体文件复用实例）。"""
        fname = self.cfg.get("lyrics_font_file")
        key = (int(size), bool(bold), fname)
        f = self._font_cache.get(key)
        if f is None:
            f = wallpaper._load_font(bold, size, fname)[0]
            self._font_cache[key] = f
        return f

    def _ensure_fonts(self):
        """按 cfg 里歌词字号/字体/窗宽重建布局与三行字体。

        样式热改（设置保存/换屏）时：窗口高、ULW 表面随之重建，并清空 _shown_pair
        强制下一帧重绘——此前只换当前行字体，下一行/译文用旧字体且不重绘（显示 bug）。
        """
        cfg = self.cfg
        _m = self.win.master
        _short = min(_m.winfo_screenwidth(), _m.winfo_screenheight()) if hasattr(_m, "winfo_screenwidth") else 1080
        px = max(12, int(_short * float(cfg.get("lyrics_size_ratio", 0.032) or 0.032)))
        fname = cfg.get("lyrics_font_file")
        W = int(int(cfg.get("lyrics_width", 420) or 420) * self.s)
        key = (px, fname, W)
        if key == self._font_key:
            return
        self._font_key = key
        self._px_cur = px
        self._px_trans = max(10, int(self._px_cur * 0.62))
        self._px_next = max(10, int(self._px_cur * 0.72))
        self._gap = max(3, self._px_cur // 8)
        self.W = W
        self.H = self._px_cur + self._px_trans + self._px_next + self._gap * 2 + self._px_cur // 2
        self._font_cur = self._load_lyr_font(self._px_cur, True)
        self._font_trans = self._load_lyr_font(self._px_trans, False)
        self._font_next = self._load_lyr_font(self._px_next, False)
        self._img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        self._draw = ImageDraw.Draw(self._img)
        self._shown_pair = None  # 强制下一帧重绘
        if getattr(self, "surface", None) is not None:  # 运行中尺寸变化：重建 ULW 表面
            try:
                self.surface.close()
            except Exception:
                pass
            self.surface = desktop.OverlaySurface(self._hwnd, self.W, self.H)

    def _fit_row(self, text: str, base_px: int, bold: bool):
        """长行自动缩小字号适配窗宽；缩到下限仍放不下则截断为省略号。返回 (font, text)。"""
        avail = max(60, self.W - int(self.s * 24))
        size = max(10, base_px)
        f = None
        while True:
            f = self._load_lyr_font(size, bold)
            if wallpaper._text_len(self._draw, text, f) <= avail or size <= 10:
                break
            size = max(10, size - max(2, size // 10))
        if wallpaper._text_len(self._draw, text, f) > avail:
            text = wallpaper._ellipsis(self._draw, text, f, avail)
        return f, text

    def _tick(self):
        try:
            if self.cfg.get("lyrics_hidden"):
                if self.win.winfo_viewable():
                    self.win.withdraw()  # 托盘/设置翻转 cfg 后这里自管理显隐
            else:
                if not self.win.winfo_viewable():
                    self.win.deiconify()
                    desktop.seat_overlays()
                self._follow()
                self._ensure_fonts()
                snap = self.ipc.snapshot()
                pos = snap["position_ms"] + 300  # 提前 300ms 切行，观感更跟手
                idx = self._current_index(pos)
                if idx != self._line_idx:
                    self._line_idx = idx
                    cur = self.lines[idx][1] if 0 <= idx < len(self.lines) else ""
                    cur_tr = self.lines[idx][2] if 0 <= idx < len(self.lines) else ""
                    nxt = self.lines[idx + 1][1] if 0 <= idx + 1 < len(self.lines) else ""
                    self._render(cur, cur_tr, nxt)
        except Exception:  # 任何异常都不能断掉 after 链（断了歌词窗就永久冻结）
            applog.log_exc("歌词 tick 异常:\n", *sys.exc_info())
        self.win.after(400, self._tick)

    def _render(self, cur: str, cur_tr: str, nxt: str):
        pair = (cur, cur_tr, nxt)
        if self._shown_pair == pair:
            return  # 内容未变不重绘
        d = self._draw
        d.rectangle((0, 0, self.W, self.H), fill=(0, 0, 0, 0))
        cfg = self.cfg
        cur_rgb = wallpaper._hex_rgb(cfg.get("lyrics_color"), (255, 255, 255))
        nxt_rgb = wallpaper._hex_rgb(cfg.get("lyrics_next_color"), (176, 176, 176))
        srgb = wallpaper._hex_rgb(cfg.get("lyrics_stroke_color"), (0, 0, 0))
        sw = max(0, min(6, int(cfg.get("lyrics_stroke_w", 2) or 0)))
        shadow_on = bool(cfg.get("lyrics_shadow", True))
        # 视觉行按需堆叠：原文 / 译文（有对照时）/ 下一行原文；整体在窗内垂直居中
        rows = []
        show_next = bool(cfg.get("lyrics_show_next", True))
        if cur:
            f, t = self._fit_row(cur, self._px_cur, True)
            rows.append((f, t, (*cur_rgb, 255), sw))
        if cur_tr:
            # 下一行隐藏时译文是唯一对照，提亮；否则按次行弱化
            tr_alpha = 235 if not (nxt and show_next) else 205
            f, t = self._fit_row(cur_tr, self._px_trans, False)
            rows.append((f, t, (*nxt_rgb, tr_alpha), max(0, sw - 1)))
        if nxt and show_next:
            f, t = self._fit_row(nxt, self._px_next, False)
            rows.append((f, t, (*nxt_rgb, 190), max(0, sw - 1)))
        total = sum(f.size for f, *_r in rows) + self._gap * (len(rows) - 1)
        y = (self.H - total) // 2
        for f, t, fill, s in rows:  # 样式与壁纸文字同源：逐字符回退 + 阴影/描边同款管线
            wallpaper._draw_shadow_text(
                self._img, (self.W / 2, y + f.size / 2), t, f,
                fill=fill, anchor="mm", shadow_alpha=170,
                stroke_width=s, stroke_fill=(*srgb, 200) if s else None,
                shadow=shadow_on)
            y += f.size + self._gap
        self._shown_pair = pair
        self.surface.update(self._img, pos=self._screen_pos())
