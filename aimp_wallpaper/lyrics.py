"""歌词获取与显示：来源 缓存 → 音频内嵌歌词 → 同目录 .lrc（纯本地，不联网）。

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
import time
import tkinter as tk
from ctypes import byref

from PIL import Image, ImageDraw

from . import applog, config, desktop, wallpaper

_STAMP = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_WORDTAG = re.compile(r"<\d+:\d+(?:\.\d+)?>")


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


# 内嵌歌词字段名（Vorbis Comment 小写比较；网易/微信导出常见 LYRICS/UNSYNCEDLYRICS）
_LYRIC_KEYS = {"lyrics", "unsyncedlyrics", "unsynced lyrics", "letra", "paroles", "歌詞"}


def _read_flac_lyrics(f) -> list[str]:
    """FLAC：遍历元数据块收集所有 VORBIS_COMMENT 里的 LYRICS 字段（可能有简繁多版本）。

    此前只看第一个 COMMENT 块就返回——歌词写在后面的 COMMENT 块时读不到。
    """
    f.seek(0)
    if f.read(4) != b"fLaC":
        return []
    found: list[str] = []
    pos, last, guard = 4, False, 0
    while not last and guard < 64:
        guard += 1
        f.seek(pos)
        hdr = f.read(4)
        if len(hdr) < 4:
            break
        last = bool(hdr[0] & 0x80)
        btype = hdr[0] & 0x7F
        length = int.from_bytes(hdr[1:4], "big")
        if btype == 4 and 0 < length < 4_000_000:  # VORBIS_COMMENT
            data = f.read(length)
            if len(data) >= 8:
                vlen = int.from_bytes(data[0:4], "little")
                p = 4 + vlen
                if p + 4 <= len(data):
                    count = int.from_bytes(data[p:p + 4], "little")
                    p += 4
                    for _ in range(min(count, 512)):
                        if p + 4 > len(data):
                            break
                        clen = int.from_bytes(data[p:p + 4], "little")
                        p += 4
                        raw = data[p:p + clen]
                        p += clen
                        if b"=" not in raw:
                            continue
                        k, v = raw.split(b"=", 1)
                        key = k.decode("ascii", "ignore").strip().lower()
                        if key in _LYRIC_KEYS:
                            text = v.decode("utf-8", "replace")
                            if text.strip():
                                found.append(text)
        pos += 4 + length
    return found


# 简繁判定用"仅繁体"字形集：出现即视为繁体（这些字简体写法不同，不会误判）
_TRAD_ONLY = set(
    "們這個來說時會後點發現現實對從還經過為與藝術機械愛語言讀寫開關門問題龍鳳寶貝號稱軍師導熱處理"
    "們東方兩個長聽見東西話謝喜歡應該還記得錯對誰讓覺得運動員區間價錢經驗應該廣場歲數責任"
    "網絡轉發選擇聯繫確認標準聲響範圍營運機構構築樂團關係歷史紀錄驗證學習練習種類豐富"
)


def _is_traditional(text: str) -> bool:
    """整段 LRC 是否以繁体为主。

    只看正文（剥离 [ti:]/[ar:] 等元数据行与时间标签），按"仅繁体字出现率"判定——
    此前把标题等元数据也算进来，个别繁体字就会误判（2026-11-11 实测踩坑）。
    """
    body = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not _STAMP.search(line):
            continue  # 空行 / 元数据行
        body.append(_STAMP.sub("", line))
    content = "".join(body)
    han = [ch for ch in content if "\u4e00" <= ch <= "\u9fff"]
    if len(han) < 8:
        return False
    hits = sum(1 for ch in han if ch in _TRAD_ONLY)
    return hits / len(han) >= 0.03  # 3% 以上属仅繁体字 → 判为繁体版


def _pick_lyrics(variants: list[str], pref: str = "zh-Hans") -> str | None:
    """同一文件里多个歌词版本时择优。pref: zh-Hans(默认,简优先) / zh-Hant / any(取第一个)。"""
    cands = [v for v in variants if v and v.strip()]
    if not cands:
        return None
    pref = str(pref or "zh-Hans")
    if pref == "zh-Hant":  # 繁体优先
        cands.sort(key=lambda t: 0 if _is_traditional(t) else 1)
    elif pref == "zh-Hans":  # 简体优先：排除繁体版本，没有简体再退回第一个
        simp = [c for c in cands if not _is_traditional(c)]
        cands = simp or cands
    return cands[0]


def _synchsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _decode_uslt_body(raw: bytes) -> str | None:
    """USLT 帧体解码：编码(1) + 语言(3) + 描述(0 结尾) + 歌词。"""
    if not raw:
        return None
    enc = raw[0]
    rest = raw[4:]  # 跳过编码+语言
    try:
        if enc == 1:  # UTF-16 with BOM
            desc_end = rest.find(b"\x00\x00")
            if desc_end < 0:
                return None
            text = rest[desc_end + 2:].decode("utf-16", "replace")
        elif enc == 2:  # UTF-16BE
            text = rest.decode("utf-16-be", "replace")
        elif enc == 3:  # UTF-8
            text = rest.split(b"\x00", 1)[-1].decode("utf-8", "replace")
        else:  # latin-1
            text = rest.split(b"\x00", 1)[-1].decode("latin-1", "replace")
    except (UnicodeDecodeError, IndexError):
        return None
    text = text.replace("\x00", "").strip()
    return text or None


def _read_id3_lyrics(f) -> str | None:
    """MP3/M4A 前部 ID3v2：找 USLT（unsigned lyrics）帧。

    v2.3/v2.4 帧头 10 字节（USLT）；v2.2 帧头 6 字节且帧名是 3 字符的 ULT——
    此前只按 10 字节头扫，v2.2 老文件的歌词永远读不到。
    """
    f.seek(0)
    head = f.read(10)
    if len(head) < 10 or head[:3] != b"ID3":
        return None
    major = head[3]
    size = _synchsafe(head[6:10])
    body = f.read(min(size, 8_000_000))
    if major < 2:
        return None
    if major == 2:
        off = 0
        while off + 6 <= len(body):
            fid = body[off:off + 3]
            if not fid.strip(b"\x00"):
                break
            fsize = int.from_bytes(body[off + 3:off + 6], "big")
            if fid == b"ULT":
                text = _decode_uslt_body(body[off + 6:off + 6 + fsize])
                if text:
                    return text
            off += 6 + fsize
        return None
    off = 0
    while off + 10 <= len(body):
        fid = body[off:off + 4]
        if not fid.strip(b"\x00"):
            break
        fsize = _synchsafe(body[off + 4:off + 8]) if major >= 4 else \
            int.from_bytes(body[off + 4:off + 8], "big")
        if fid == b"USLT":
            text = _decode_uslt_body(body[off + 10:off + 10 + fsize])
            if text:
                return text
        off += 10 + fsize
    return None


def _read_embedded_lyrics(audio_path: str, pref: str = "zh-Hans") -> str | None:
    """读音频文件内嵌歌词：FLAC(Vorbis COMMENT) → ID3v2 USLT。失败 None。"""
    if not audio_path or not os.path.isfile(audio_path):
        return None
    try:
        with open(audio_path, "rb") as f:
            ext = os.path.splitext(audio_path)[1].lower()
            if ext == ".flac":
                return _pick_lyrics(_read_flac_lyrics(f) or [], pref)
            if ext in (".mp3", ".m4a", ".aac", ".wav", ".aiff"):
                return _read_id3_lyrics(f)
            # 其它容器（ape/ogg 等）先试 FLAC 结构再试 ID3
            picked = _pick_lyrics(_read_flac_lyrics(f) or [], pref)
            return picked if picked else _read_id3_lyrics(f)
    except OSError:
        return None


def _local_lrc_candidates(audio_path: str, title: str) -> list[str]:
    cands = []
    if audio_path and os.path.isabs(audio_path):
        base = os.path.splitext(audio_path)[0]
        cands.append(base + ".lrc")
        cands.append(os.path.join(os.path.dirname(audio_path), title.strip() + ".lrc"))
    return cands


def _pair_lyrics(orig: list[tuple[int, str]], trans_lines: list[tuple[int, str]] | None = None):
    """合并原文/翻译 → [(ms, 原文, 翻译)]。

    网易云：tlyric 按时间戳精确配对；本地双语 LRC：同时间戳连续双行（内容不同），
    第二行视为翻译——完全相同的重复行是副歌回声，不吞（此前会被当翻译隐藏）。
    """
    tmap: dict[int, str] = {}
    for ms, t in (trans_lines or []):
        tmap.setdefault(ms, t)
    out: list[tuple[int, str, str]] = []
    i = 0
    while i < len(orig):
        ms, text = orig[i]
        tr = tmap.get(ms, "")
        if not tr and i + 1 < len(orig) and orig[i + 1][0] == ms and orig[i + 1][1] != text:
            tr = orig[i + 1][1]
            i += 1
        out.append((ms, text, tr))
        i += 1
    return out


def fetch_lrc(title: str, artist: str, duration_ms: int | None,
              cache_dir: str, audio_path: str | None = None,
              lang_pref: str = "zh-Hans"):
    """歌词来源：缓存 → 音频内嵌歌词 → 同目录 .lrc。找不到返回 None（不联网）。

    返回 [(ms, 原文, 翻译)]（翻译可为空串）。
    """
    os.makedirs(cache_dir, exist_ok=True)
    # 缓存键必须含语言偏好：简/繁优先是不同的择优结果，共用一份缓存会让
    # 「多语言优先」设置对已抓过的歌永远不生效
    key = hashlib.md5(f"{title.lower()}|{artist.lower()}|{lang_pref}".encode("utf-8")).hexdigest()
    cache_file = os.path.join(cache_dir, key + ".lrc")

    lrc_text = None
    tlyric_text = None
    from_cache = False
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                lrc_text = f.read()
            from_cache = bool(lrc_text)
        except OSError:
            lrc_text = None
    if lrc_text is None:  # 1) 内嵌歌词（FLAC 的 LYRICS 字段 / ID3 USLT）
        lrc_text = _read_embedded_lyrics(audio_path or "", lang_pref)
    if lrc_text is None:  # 2) 同目录 .lrc 文件
        for cand in _local_lrc_candidates(audio_path or "", title):
            if os.path.exists(cand):
                for enc in ("utf-8", "gbk", "utf-16"):
                    try:
                        with open(cand, "r", encoding=enc) as f:
                            lrc_text = f.read()
                        break
                    except (OSError, UnicodeDecodeError):
                        continue
                if lrc_text:
                    break
    if not lrc_text:
        return None
    lines = parse_lrc(lrc_text)
    if lines and tlyric_text:
        lines = _pair_lyrics(lines, parse_lrc(tlyric_text))
    elif lines:
        lines = _pair_lyrics(lines)
    if lines and not from_cache:  # 缓存命中不再回写（重复 I/O 且会抹掉原始 LRC 元数据）
        try:  # 回写规范化结果（翻译行与原文同时间戳）
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
                # key 必须含语言偏好：切简/繁后当前歌要重抓（此前不切歌不生效）
                key = (snap["title"], snap["artist"], self.cfg.get("lyrics_lang_pref", "zh-Hans"))
                if key == self._key:
                    continue
                self._key = key
                lines = fetch_lrc(snap["title"], snap["artist"], snap["duration_ms"] or None,
                                  self.cfg["output_dir"], snap.get("filename"),
                                  self.cfg.get("lyrics_lang_pref", "zh-Hans"))
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
        self.pad = int(4 * self.s)  # 与 vis_panel.pad 一致，保证左缘对齐
        self.lines: list[tuple[int, str]] = []
        self._times: list[int] = []  # 歌词未就绪时 _tick 也要能跑（set_lines 前不存在会炸链）
        self._line_idx = -1
        self._shown_pair = None
        self._drag = None
        self._want = (0, 0)
        self._want_mtime = 0
        self._anchor_mtime = 0
        self._anchor_cache = None
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
        self._menu.add_command(label="恢复跟随", command=self._follow_again)
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
        """跟随壁纸排版：读渲染锚点，mtime 未变走缓存（与频谱面板同实现）。返回 (pos | None, mtime)。"""
        p = os.path.join(self.cfg["output_dir"], "vis_anchor.json")
        try:
            mtime = os.stat(p).st_mtime
        except OSError:
            return None, 0
        if mtime == self._anchor_mtime:
            return self._anchor_cache, mtime
        pos = None
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            pos = (int(d["x"]), int(d["y"]))
        except (OSError, ValueError, KeyError):
            pos = None
        self._anchor_mtime = mtime
        self._anchor_cache = pos
        return pos, mtime

    def _auto_pos(self):
        """自动位置（与频谱面板同构）：按跟随模式算目标，最后钳制在虚拟桌面内。

        与频谱面板的间距/上下位置由 lyrics_gap / lyrics_side 控制（都可调）。
        兜底位置锚主屏工作区；钳制用虚拟屏——面板拖到副屏时不被拽回主屏。
        """
        mode = self.cfg.get("lyrics_follow", "panel")
        wa_l, wa_t, wa_r, wa_b = desktop.work_area()
        gap = max(0, int(self.cfg.get("lyrics_gap", 6) or 0)) * int(self.s)
        above = self.cfg.get("lyrics_side", "below") == "above"
        if mode == "anchor":
            pos, _ = self._anchor_pos()
            if pos:
                y = (pos[1] - self.H - gap) if above else (pos[1] + gap)
                x = pos[0]
            else:
                x, y = wa_r - self.W - int(24 * self.s), wa_b - self.H - int(14 * self.s)
        elif mode == "fixed":
            x, y = wa_r - self.W - int(24 * self.s), wa_b - self.H - int(14 * self.s)
        else:  # panel：贴频谱面板（上方或下方）
            panel_pos = self.get_panel_pos()
            if panel_pos:
                px_, py_ = panel_pos
                y = (py_ - self.H - gap) if above else (py_ + self.H_panel() + gap)
                x = px_
            else:
                x, y = wa_r - self.W - int(24 * self.s), wa_b - self.H - int(14 * self.s)
        vx_l, vx_t, vx_r, vx_b = desktop.virtual_screen()
        x = max(vx_l, min(x, vx_r - self.W))
        y = max(vx_t, min(y, vx_b - self.H))
        return x, y

    def H_panel(self) -> int:
        return int(self.cfg.get("vis_height", 120) * self.s)

    def _place_initial(self):
        pos = self.cfg.get("lyrics_pos")
        if pos and len(pos) == 2:
            x, y = int(pos[0]), int(pos[1])
        else:
            x, y = self._auto_pos()
        self.win.geometry(f"+{x}+{y}")
        self._want = (x, y)

    def _screen_pos(self):
        r = desktop.wintypes.RECT()
        desktop.user32.GetWindowRect(self._hwnd, byref(r))
        return (int(r.left), int(r.top))

    def _follow_anchor(self):
        """与频谱面板一致：手动定位后不跟；锚点文件变化或面板移动时才挪窗。"""
        if self.cfg.get("lyrics_pos"):
            return
        mode = self.cfg.get("lyrics_follow", "panel")
        if mode == "fixed":
            return
        moved = False
        if mode == "anchor":
            pos, mtime = self._anchor_pos()
            if pos and mtime != getattr(self, "_want_mtime", 0):
                self._want_mtime = mtime
                moved = True
        else:  # panel：面板可能被拖动，位置每帧都纠一次（代价极小）
            moved = True
        x, y = self._auto_pos()
        if moved and (x, y) != self._want:
            self._want = (x, y)
            self.win.geometry(f"+{x}+{y}")
            if self.surface is not None:
                self.surface.update(self._img, pos=(x, y))  # ULW 内容随窗口一起走

    def _move_to(self, x: int, y: int):
        self._want = (x, y)
        self.win.geometry(f"+{x}+{y}")

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

    def _follow_again(self):
        """清掉拖动坐标，回到面板跟随（固定模式的"复活"入口）。"""
        self.cfg["lyrics_pos"] = None
        config.save(self.cfg)
        self._anchor_mtime = 0
        self._want_mtime = 0
        self._follow_anchor()

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
        self.cfg["lyrics_pos"] = [nx, ny]  # 拖过后粘滞（与频谱面板同语义）
        self._move_to(nx, ny)
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

    def _cut_to_width(self, text: str, f, avail: int) -> int:
        """二分找 avail 内能放下的最大前缀长度。"""
        lo, hi = 1, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if wallpaper._text_len(self._draw, text[:mid], f) <= avail:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def _wrap_lyric(self, text: str, f, avail: int, max_lines: int):
        """按宽度贪心折行（优先断在空格）。返回 (行列表, 未显示的剩余文本)。"""
        lines, rest = [], text
        while rest and len(lines) < max_lines:
            rest = rest.lstrip()
            if not rest:
                break
            cut = self._cut_to_width(rest, f, avail)
            sp = rest.rfind(" ", 0, cut + 1)  # 优先断在空格（空格位置不太靠前时）
            if sp > 0:
                cut = sp
            lines.append(rest[:cut].rstrip())
            rest = rest[cut:].lstrip()
        return lines, rest

    def _layout_row(self, text: str, base_px: int, bold: bool, max_lines: int = 2):
        """长句排版：字号有下限（不低于 base 的 55% 且 ≥14px，避免缩成小字），
        超宽按词折行 ≤max_lines 行，仍放不下才省略号。返回 (font, px, [行文本])。"""
        avail = max(60, self.W - 2 * self.pad)
        floor = max(14, int(base_px * 0.55))
        size = base_px
        while size > floor:
            f = self._load_lyr_font(size, bold)
            if wallpaper._text_len(self._draw, text, f) <= avail:
                return f, size, [text]
            size = max(floor, size - max(2, size // 8))
        f = self._load_lyr_font(size, bold)
        lines, rest = self._wrap_lyric(text, f, avail, max_lines)
        if rest:  # 折满仍放不下：末行省略号截断
            lines[-1] = wallpaper._ellipsis(self._draw, lines[-1], f, avail)
        return f, size, lines

    def _tick(self):
        try:
            if time.monotonic() - getattr(self, "_last_maint", 0) >= 1.0:
                self._last_maint = time.monotonic()
                self._lock_var.set(bool(self.cfg.get("lyrics_locked")))  # 设置改动后同步右键菜单
            if self.cfg.get("lyrics_hidden"):
                if self.win.winfo_viewable():
                    self.win.withdraw()  # 托盘/设置翻转 cfg 后这里自管理显隐
            else:
                if not self.win.winfo_viewable():
                    self.win.deiconify()
                    desktop.seat_overlays()
                self._follow_anchor()
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
        # 视觉行按需堆叠：原文（可折 2 行）/ 译文 / 下一行；整体在窗内垂直居中
        rows = []
        show_next = bool(cfg.get("lyrics_show_next", True))
        show_trans = bool(cfg.get("lyrics_show_trans", True))
        if cur:
            f, px, ls = self._layout_row(cur, self._px_cur, True, max_lines=2)
            for t in ls:
                rows.append((f, t, (*cur_rgb, 255), sw))
        if cur_tr and show_trans:
            # 只剩当前行(原文)时译文是唯一对照，提亮；否则按次行弱化
            tr_alpha = 235 if not (nxt and show_next) else 205
            f, _px, (t,) = self._layout_row(cur_tr, self._px_trans, False, max_lines=1)
            rows.append((f, t, (*nxt_rgb, tr_alpha), max(0, sw - 1)))
        if nxt and show_next:
            f, _px, (t,) = self._layout_row(nxt, self._px_next, False, max_lines=1)
            rows.append((f, t, (*nxt_rgb, 190), max(0, sw - 1)))
        total = sum(f.size for f, *_r in rows) + self._gap * (len(rows) - 1)
        y = (self.H - total) // 2
        x0 = self.pad  # 左对齐：与频谱面板左缘同一内边距
        for f, t, fill, s in rows:  # 样式与壁纸文字同源：逐字符回退 + 阴影/描边同款管线
            wallpaper._draw_shadow_text(
                self._img, (x0, y + f.size / 2), t, f,
                fill=fill, anchor="lm", shadow_alpha=170,
                stroke_width=s, stroke_fill=(*srgb, 200) if s else None,
                shadow=shadow_on)
            y += f.size + self._gap
        self._shown_pair = pair
        self.surface.update(self._img, pos=self._screen_pos())
