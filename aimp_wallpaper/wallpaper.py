"""海报式壁纸渲染 + 多屏设置。

布局（用户选定）：背景=封面放大铺满+高斯模糊+压暗；前景=清晰封面偏左，右侧歌名/歌手—专辑。
设置壁纸用 comtypes 手写 COM 接口 IDesktopWallpaper，逐显示器 SetWallpaper + DWPOS_FILL。
"""
from __future__ import annotations

import io
import json
import os
import re
import time

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import config

# ---- comtypes: IDesktopWallpaper（虚表顺序必须完整声明到所用槽位）----
import comtypes
from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
from ctypes import POINTER, wintypes

CLSID_DesktopWallpaper = GUID("{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}")
DWPOS_CENTER, DWPOS_TILE, DWPOS_STRETCH, DWPOS_FIT, DWPOS_FILL, DWPOS_SPAN = 0, 1, 2, 3, 4, 5


class IDesktopWallpaper(IUnknown):
    _iid_ = GUID("{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}")
    _methods_ = [
        COMMETHOD([], HRESULT, "SetWallpaper",
                  (["in"], wintypes.LPCWSTR, "monitorID"),
                  (["in"], wintypes.LPCWSTR, "wallpaper")),
        COMMETHOD([], HRESULT, "GetWallpaper",
                  (["in"], wintypes.LPCWSTR, "monitorID"),
                  (["out"], POINTER(wintypes.LPWSTR), "wallpaper")),
        COMMETHOD([], HRESULT, "GetMonitorDevicePathAt",
                  (["in"], wintypes.UINT, "index"),
                  (["out"], POINTER(wintypes.LPWSTR), "monitorID")),
        COMMETHOD([], HRESULT, "GetMonitorDevicePathCount",
                  (["out"], POINTER(wintypes.UINT), "count")),
        COMMETHOD([], HRESULT, "GetMonitorRECT",
                  (["in"], wintypes.LPCWSTR, "monitorID"),
                  (["out"], POINTER(wintypes.RECT), "rect")),
        COMMETHOD([], HRESULT, "SetBackgroundColor",
                  (["in"], wintypes.COLORREF, "color")),
        COMMETHOD([], HRESULT, "GetBackgroundColor",
                  (["out"], POINTER(wintypes.COLORREF), "color")),
        COMMETHOD([], HRESULT, "SetPosition",
                  (["in"], wintypes.DWORD, "position")),
        COMMETHOD([], HRESULT, "GetPosition",
                  (["out"], POINTER(wintypes.DWORD), "position")),
    ]


def _get_wallpaper_com():
    return comtypes.CoCreateInstance(CLSID_DesktopWallpaper, interface=IDesktopWallpaper)


_MON_CACHE: tuple | None = None


def get_monitors() -> list[dict]:
    """[{id, w, h, left, top}]，物理像素（进程已声明 per-monitor DPI aware）。

    系统会登记已断开的显示器（如合盖外接时的笔记本屏），对它 GetMonitorRECT 抛
    COMError(E_FAIL)，而 COMError 不是 OSError 子类——必须宽捕，否则单块屏失败
    会让整次渲染崩掉（2026-11-09 壁纸不更新的真因）。
    """
    global _MON_CACHE
    now = time.monotonic()
    if _MON_CACHE and now - _MON_CACHE[0] < 10.0:
        return [dict(m) for m in _MON_CACHE[1]]
    dw = _get_wallpaper_com()
    monitors = []
    count = dw.GetMonitorDevicePathCount()
    for i in range(count):
        mid = dw.GetMonitorDevicePathAt(i)
        if not mid:
            continue
        try:
            rc = dw.GetMonitorRECT(mid)
            w, h = rc.right - rc.left, rc.bottom - rc.top
        except Exception:  # COMError / OSError：断开的显示器跳过
            continue
        if w > 0 and h > 0:
            monitors.append({"id": mid, "w": w, "h": h, "left": int(rc.left), "top": int(rc.top)})
    if monitors:  # 缓存 10s：显示器很少变，省掉每次渲染的 COM 往返
        _MON_CACHE = (now, monitors)
    return [dict(m) for m in monitors]


_STYLE_WORDS = {"regular", "bold", "light", "medium", "heavy", "black", "italic", "oblique",
                "thin", "semibold", "extrabold", "extra-bold", "粗体", "常规", "细体", "中等", "标准"}
_FONT_ENTRIES: list[tuple[str, str]] | None = None  # [(注册标签, 文件名/全路径)]


def font_entries() -> list[tuple[str, str]]:
    """注册表枚举已装字体（进程内缓存一次）。"""
    global _FONT_ENTRIES
    if _FONT_ENTRIES is not None:
        return _FONT_ENTRIES
    import winreg
    out: dict[tuple[str, str], None] = {}
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        except OSError:
            continue
        with key:
            i = 0
            while True:
                try:
                    name, fname, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1
                fname = str(fname).strip()
                if not fname.lower().endswith((".ttf", ".ttc", ".otf")):
                    continue
                label = re.sub(r"\s*[（(](TrueType|OpenType)[^)）]*[)）]\s*$", "", str(name)).strip()
                if label:
                    out.setdefault((label, fname))
    _FONT_ENTRIES = sorted(out)
    return _FONT_ENTRIES


def _bold_variant(font_file: str) -> str | None:
    """在同家族里找真实 Bold 字面文件；找不到返回 None。结果按进程缓存。"""
    cache = getattr(_bold_variant, "_cache", None)
    if cache is None:
        cache = _bold_variant._cache = {}
    if font_file in cache:
        return cache[font_file]
    result = None
    base = os.path.basename(font_file).lower()
    for label, fname in font_entries():
        if os.path.basename(fname).lower() == base:
            family = " ".join(w for w in label.split() if w.lower().strip("-") not in _STYLE_WORDS)
            break
    else:
        family = None
    if family:
        for label, fname in font_entries():
            if fname == font_file:
                continue
            low = label.lower()
            if low.startswith(family.lower()) and "bold" in low:
                result = fname
                break
    cache[font_file] = result
    return result


def _load_font(bold: bool, size: int, font_file: str | None = None) -> tuple[ImageFont.FreeTypeFont, bool]:
    """返回 (font, real_bold)。real_bold=True 表示已是真实粗体（粗体字面/可变字体实例），无需描边。"""
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    if font_file:
        if bold:  # 1) 同家族真实 Bold 字面
            bf = _bold_variant(font_file)
            if bf:
                try:
                    return ImageFont.truetype(bf if os.path.isabs(bf) else os.path.join(fonts_dir, bf), size), True
                except OSError:
                    pass
        try:
            font = ImageFont.truetype(font_file if os.path.isabs(font_file) else os.path.join(fonts_dir, font_file), size)
            if bold:  # 2) 可变字体 Bold 实例
                try:
                    font.set_variation_by_name("Bold")
                    return font, True
                except Exception:
                    pass
            return font, False  # 3) 交给调用方轻描边
        except OSError:
            pass
    # 默认字体链：雅黑 → 雅黑常规 → 黑体 → 宋体 → 等线 → Segoe UI（别的机器可能缺某个）
    bold_first = ("msyhbd.ttc", "msyh.ttc") if bold else ("msyh.ttc", "msyhbd.ttc")
    for name in bold_first + ("simhei.ttf", "simsun.ttc", "Deng.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(os.path.join(fonts_dir, name), size), bold
        except OSError:
            continue
    return ImageFont.load_default(size), False


def _placeholder_bg(w: int, h: int) -> Image.Image:
    bg = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(bg)
    top, bottom = (34, 40, 54), (16, 18, 26)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return bg


def _cover_fit_full(im: Image.Image, w: int, h: int) -> Image.Image:
    """等比放大铺满再居中裁剪（全分辨率 LANCZOS）。"""
    im = im.convert("RGB")
    scale = max(w / im.width, h / im.height)
    im = im.resize((max(w, int(im.width * scale + 0.5)), max(h, int(im.height * scale + 0.5))), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _dominant_color(cover: Image.Image) -> tuple[int, int, int]:
    """封面平均主色（适度提饱和，偏暗时多提）。"""
    small = np.asarray(cover.convert("RGB").resize((40, 40)), dtype=np.float64)
    r, g, b = small[..., 0].mean(), small[..., 1].mean(), small[..., 2].mean()
    mx = max(r, g, b)
    boost = 1.25 if mx > 40 else 1.8
    return (min(255, int(r * boost)), min(255, int(g * boost)), min(255, int(b * boost)))


def _vignette(img: Image.Image, strength: int = 120) -> Image.Image:
    """叠加上透下暗的黑色渐变（电影感）。"""
    w, h = img.size
    grad = Image.new("L", (1, h))
    for y in range(h):
        grad.putpixel((0, y), int(strength * (y / max(1, h - 1)) ** 1.2))
    grad = grad.resize((w, h))
    out = img.convert("RGBA")
    black = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    black.putalpha(grad)
    out.alpha_composite(black)
    return out.convert("RGB")


_DARK_CACHE: tuple | None = None


def _system_dark_mode() -> bool:
    """Windows 日/夜主题：SystemUsesLightTheme 优先（桌面配系统模式），缺省回 AppsUseLightTheme（1=浅色）。"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
    except OSError:
        return False
    with key:
        for name in ("SystemUsesLightTheme", "AppsUseLightTheme"):
            try:
                v, _ = winreg.QueryValueEx(key, name)
                return int(v) == 0
            except OSError:
                continue
    return False


def system_is_dark() -> bool:
    """系统是否处于深色（夜间）主题，结果缓存 2s。"""
    global _DARK_CACHE
    now = time.monotonic()
    if _DARK_CACHE and now - _DARK_CACHE[0] < 2.0:
        return _DARK_CACHE[1]
    v = _system_dark_mode()
    _DARK_CACHE = (now, v)
    return v


def _night_alpha(cfg: dict) -> int:
    """夜间黑色遮罩的 alpha：开启跟随且系统处于深色主题时生效（0=不叠加）。"""
    if not cfg.get("theme_night_follow"):
        return 0
    if not system_is_dark():
        return 0
    pct = max(0, min(95, int(cfg.get("night_overlay", 30) or 0)))
    return pct * 255 // 100


def _apply_blur_type(base: Image.Image, cfg: dict) -> Image.Image:
    """模糊类型分发（blur/blur_vignette 方案下生效，都在 1/4 小图上算）。

    只保留高斯系四变体（视觉都在"柔糊"一族，无拖影/扭曲/像素化类效果）：
    gauss=标准高斯（默认）/ soft=柔焦（两级高斯混合，更奶油）/ fog=雾面（重度降采样，均匀雾）/
    glow=辉光（双层高斯屏幕混合，微微发光）。
    """
    r = max(4, int(cfg.get("blur_radius", 28) or 28))
    t = cfg.get("blur_type", "gauss")
    if t == "soft":
        # 柔焦：1/4 与 1/8 两级高斯按 55/45 混合，过渡更奶油、更梦幻
        blurred = base.filter(ImageFilter.GaussianBlur(radius=r / 4.0))
        tiny = base.resize((max(2, base.width // 2), max(2, base.height // 2)), Image.BOX)
        creamy = tiny.filter(ImageFilter.GaussianBlur(radius=r / 6.0)).resize(base.size, Image.BILINEAR)
        return Image.blend(blurred, creamy, 0.45)
    if t == "fog":
        # 雾面：重度降采样（倍率随强度）+ 轻高斯再放大，结构化为均匀雾
        sw, sh = base.size
        k = max(2, r // 12)
        fog = base.resize((max(2, sw // k), max(2, sh // k)), Image.BOX)
        fog = fog.filter(ImageFilter.GaussianBlur(radius=2.0))
        return fog.resize((sw, sh), Image.BILINEAR)
    if t == "glow":
        # 辉光：两个半径的高斯做屏幕混合（255-(255-a)(255-b)/255），高光区微微发光
        b1 = np.asarray(base.filter(ImageFilter.GaussianBlur(radius=r / 4.0)), dtype=np.float64)
        b2 = np.asarray(base.filter(ImageFilter.GaussianBlur(radius=r / 2.0)), dtype=np.float64)
        out = 255.0 - (255.0 - b1) * (255.0 - b2) / 255.0
        return Image.fromarray(out.astype(np.uint8))
    return base.filter(ImageFilter.GaussianBlur(radius=r / 4.0))


def _blur_bg(cover: Image.Image | None, w: int, h: int, cfg: dict) -> Image.Image:
    """背景方案分发：blur=模糊 / blur_vignette=模糊+暗角 / sharp=原图铺满 / gradient=主色渐变。

    blur 类方案的模糊算法由 blur_type 决定（高斯/柔焦/雾面/辉光，同属高斯系）。
    跟随日夜主题时，深色主题再叠一层黑色遮罩（浓度=night_overlay%）。
    """
    style = cfg.get("bg_style", "blur")
    if cover is None:
        bg = _placeholder_bg(w, h)
    elif style == "sharp":
        bg = _cover_fit_full(cover, w, h)
        bg = ImageEnhance.Brightness(bg).enhance(cfg["darken"])
    elif style == "gradient":
        base = _dominant_color(cover)
        k = float(cfg["darken"])
        top = tuple(int(c * 0.30 * k / max(0.75, k)) for c in base)
        bottom = tuple(min(255, int(c * 0.75 * max(0.75, k))) for c in base)
        bg = Image.new("RGB", (w, h))
        d = ImageDraw.Draw(bg)
        for y in range(h):
            t = y / max(1, h - 1)
            d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    else:
        # blur / blur_vignette：背景本身就是模糊图，1/4 尺寸上算完再放大（BOX 缩小最快，视觉无差）
        sw, sh = max(2, w // 4), max(2, h // 4)
        im = cover.convert("RGB")
        scale = max(sw / im.width, sh / im.height)
        im = im.resize((max(sw, int(im.width * scale + 0.5)), max(sh, int(im.height * scale + 0.5))), Image.BOX)
        x, y = (im.width - sw) // 2, (im.height - sh) // 2
        bg = _apply_blur_type(im.crop((x, y, x + sw, y + sh)), cfg)
        # 亮度/饱和度是逐像素运算，在小图上做与大图等价（省 ~12ms）
        bg = ImageEnhance.Brightness(bg).enhance(cfg["darken"])
        bg = ImageEnhance.Color(bg).enhance(0.9)
        bg = bg.resize((w, h), Image.BILINEAR)
        if style == "blur_vignette":
            bg = _vignette(bg, 120)
    alpha = _night_alpha(cfg)
    if alpha:  # 夜间遮罩：统一在成品上叠黑，对四种方案都生效
        bg = bg.convert("RGBA")
        bg.alpha_composite(Image.new("RGBA", bg.size, (0, 0, 0, alpha)))
        bg = bg.convert("RGB")
    return bg


# ---------- 字体回退（PIL 不做系统级字体回退，缺字形会画方框） ----------

_FALLBACK_FONTS = ("seguisym.ttf", "tahoma.ttf", "msyh.ttc", "seguiemj.ttf")
_GLYPH_CACHE: dict[tuple, bool] = {}
_FB_FONT_CACHE: dict[tuple, object] = {}
_NOTDEF_SIG_CACHE: dict[tuple, tuple] = {}


def _mask_sig(font, ch):
    try:
        m = font.getmask(ch, mode="L")
    except Exception:
        return None
    data = m.tobytes() if hasattr(m, "tobytes") else bytes(m)
    return (m.size, data)


def _has_glyph(font, ch: str) -> bool:
    """字体是否真的含该字符字形（用「与 .notdef 渲染结果是否完全一致」判定）。"""
    if ch.isspace():
        return True
    key = (getattr(font, "path", ""), font.size, ch)
    hit = _GLYPH_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        notdef_key = (getattr(font, "path", ""), font.size)
        notdef = _NOTDEF_SIG_CACHE.get(notdef_key)
        if notdef is None:
            notdef = _mask_sig(font, "\uffff")
            _NOTDEF_SIG_CACHE[notdef_key] = notdef
        sig = _mask_sig(font, ch)
        ok = sig is not None and notdef is not None and sig != notdef
    except Exception:
        ok = True  # 判断不了就按"有"处理，避免误切字体
    _GLYPH_CACHE[key] = ok
    return ok


def _font_at(size: int, fname: str | None):
    """按像素字号+文件名取字体（带缓存）。fname 为 None 表示默认雅黑加粗档。"""
    if not fname:
        return None
    key = (size, fname)
    f = _FB_FONT_CACHE.get(key)
    if f is None:
        fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        try:
            f = ImageFont.truetype(
                fname if os.path.isabs(fname) else os.path.join(fonts_dir, fname), size)
        except OSError:
            f = False
        _FB_FONT_CACHE[key] = f
    return f or None


def _fallback_font(primary, size: int, ch: str):
    """为主字体补一个能显示 ch 的回退字体；找不到就返回主字体。"""
    for fname in _FALLBACK_FONTS:
        f = _font_at(size, fname)
        if f is not None and _has_glyph(f, ch):
            return f
    return primary


def _text_runs(text: str, font):
    """把文本切成 [(片段, 字体)]，缺字形的字用回退字体。"""
    if not text:
        return []
    runs: list[list] = []
    for ch in text:
        f = font if _has_glyph(font, ch) else _fallback_font(font, font.size, ch)
        if runs and runs[-1][1] is f:
            runs[-1][0] += ch
        else:
            runs.append([ch, f])
    return [(t, f) for t, f in runs]


def _text_len(draw, text: str, font) -> float:
    """含回退字体的文本宽度。"""
    total = 0.0
    for chunk, f in _text_runs(text, font):
        total += draw.textlength(chunk, font=f)
    return total


def _draw_runs(d, x: float, y: float, runs, fill, anchor: str,
               stroke_width: int = 0, stroke_fill=None, base_ascent: int = 0):
    """按 anchor（'la'/'ma'/'ra'）绘制多字体文本；非首段按 ascent 差对齐基线。"""
    widths = [d.textlength(t, font=f) for t, f in runs]
    total = sum(widths)
    start = x - total / 2 if anchor.startswith("m") else (x - total if anchor.startswith("r") else x)
    cur = start
    sf = stroke_fill if (stroke_width and stroke_fill is not None) else (fill if stroke_width else None)
    for (t, f), w in zip(runs, widths):
        dy = base_ascent - f.getmetrics()[0]
        d.text((cur, y + dy), t, font=f, fill=fill, anchor="l" + anchor[1],
               stroke_width=stroke_width, stroke_fill=sf)
        cur += w


def _ellipsis(draw, text, font, max_w):
    """单行省略号截断（宽度按字体回退后的实际宽度算）。"""
    if _text_len(draw, text, font) <= max_w:
        return text
    while text and _text_len(draw, text + "…", font) > max_w:
        text = text[:-1]
    return (text + "…") if text else "…"


_OPEN_BRACKETS = "（(「『【〔［｛{《〈"
_CLOSE_BRACKETS = "）)』」】〕］｝}》〉"


def _find_close(text: str, i: int, end: int) -> int:
    """在 text[i:end) 里找第一个闭合括号，找不到返回 -1。"""
    for k in range(i, min(end, len(text))):
        if text[k] in _CLOSE_BRACKETS:
            return k
    return -1


def _scan_open(seg: str, pos0: int, cur_open: int) -> int:
    """吸收段 seg（原文从 pos0 起）后返回未闭合开括号位置（-1=无；嵌套不深究，闭合即清）。"""
    for k, c in enumerate(seg):
        if c in _OPEN_BRACKETS:
            if cur_open < 0:
                cur_open = pos0 + k
        elif c in _CLOSE_BRACKETS:
            cur_open = -1
    return cur_open


def _wrap_title(draw, text, font, max_w, max_lines=4, space_window=0, bracket_break=False,
                line_limit=None):
    """超宽处理：按像素宽度折行，最多 max_lines 行（默认 4），超限直接截断、无省略号——
    换行模式就是要看到全文，省略号由 overflow=ellipsis 单行模式负责。

    space_window>0：折行点的剩余部分前 space_window 个字符内有空格时，
    断点移到该空格后（避免把短词组切碎）。
    bracket_break=True：断点落在括号组内部时——闭合括号就在跟前（space_window
    个字符内）则吸收闭合括号、把组完整留在本行；否则整组挪到下一行（组从行首
    就开始时退回普通断行）。
    line_limit：单行硬宽度上限（像素，通常=文字起点到屏幕右缘的预算）。空格/括号
    吸收后若超限则放弃吸收——**任何行都绝不超过屏幕可用宽度**（2026-11-10 修复：
    括号吸收无宽度上限，CJK 吸 3 字 ≈170px 把行顶出屏幕被裁）。
    """
    if max_lines <= 1:
        return [_ellipsis(draw, text, font, max_w)]
    if _text_len(draw, text, font) <= max_w:
        return [text]
    lines, cur = [], ""
    i, n = 0, len(text)
    line_start = 0   # 当前正在累积的这一行在原文里的起点
    open_pos = -1    # 本行未闭合的开括号位置（-1=不在括号内）

    def _fits(s):
        return line_limit is None or _text_len(draw, s, font) <= line_limit

    while i < n:
        ch = text[i]
        if cur and _text_len(draw, cur + ch, font) > max_w:
            moved = False
            if bracket_break and open_pos >= 0:
                close_j = _find_close(text, i, i + space_window) if space_window > 0 else -1
                if close_j >= 0 and _fits(text[line_start:close_j + 1]):
                    seg = text[i:close_j + 1]  # 小尾巴吸收闭合括号，组完整留在本行
                    cur += seg
                    open_pos = _scan_open(seg, i, open_pos)
                    i = close_j + 1
                    moved = True
                elif open_pos > line_start:
                    cur = text[line_start:open_pos]  # 组整体挪到下一行
                    i = open_pos
                    moved = True
                # open_pos == line_start（组占满整行）→ 退回普通断行
            if not moved and space_window > 0:
                j = text.find(" ", i, i + space_window)
                if j >= 0 and _fits(text[line_start:j + 1]):
                    # 吸收到空格（含空格），在空格后直接换行（超 line_limit 则放弃）
                    seg = text[i:j + 1]
                    cur += seg
                    open_pos = _scan_open(seg, i, open_pos)
                    i = j + 1
                    moved = True
            lines.append(cur.rstrip())
            cur = ""
            open_pos = -1
            if len(lines) == max_lines:  # 达到行数上限：直接截断（换行模式无省略号）
                break
            while i < n and text[i] == " ":  # 断行后跳过前导空格（居中/右对齐会偏移）
                i += 1
            line_start = i
        else:
            cur += ch
            if bracket_break:
                open_pos = _scan_open(ch, i, open_pos)
            i += 1
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


def _draw_shadow_text(layer, xy, text, font, fill=(255, 255, 255, 255), anchor="la",
                      shadow_alpha=140, stroke_width=0, stroke_fill=None, shadow=True):
    """逐字符字体回退后再绘制（避免缺字形画方框）。stroke_fill=描边色（None=随字色）。"""
    d = ImageDraw.Draw(layer)
    x, y = xy
    off = max(2, font.size // 24)
    runs = _text_runs(text, font)
    if not runs:
        return
    ascent = font.getmetrics()[0]
    if shadow:
        _draw_runs(d, x + off, y + off, runs, (0, 0, 0, shadow_alpha), anchor,
                   stroke_width=stroke_width, stroke_fill=(0, 0, 0, shadow_alpha),
                   base_ascent=ascent)
    _draw_runs(d, x, y, runs, fill, anchor, stroke_width=stroke_width,
               stroke_fill=stroke_fill, base_ascent=ascent)


def _rounded(im: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=radius, fill=255)
    im = im.convert("RGBA")
    im.putalpha(mask)
    return im


def _hex_rgb(value, default: tuple[int, int, int]) -> tuple[int, int, int]:
    """'#RRGGBB' → (r,g,b)；非法回退 default。"""
    try:
        s = str(value).strip().lstrip("#")
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except (ValueError, TypeError):
        pass
    return default


# ---------- 歌曲信息行：音频文件头解析（FLAC/WAV/MP3）+ 模板渲染 ----------

_FMT_NAMES = {".flac": "FLAC", ".mp3": "MP3", ".ape": "APE", ".wav": "WAV", ".ogg": "OGG",
              ".m4a": "M4A", ".aac": "AAC", ".wv": "WV", ".tta": "TTA", ".dsf": "DSF",
              ".opus": "OPUS", ".wma": "WMA"}
_AUDIO_INFO_CACHE: dict = {}


def _flac_info(data: bytes):
    """STREAMINFO → (采样率, 位深, 总样本数)。"""
    if data[:4] != b"fLaC" or len(data) < 42:
        return None
    b = data[8:42]  # 跳过块头，STREAMINFO 34 字节
    sr = (b[10] << 12) | (b[11] << 4) | (b[12] >> 4)
    bps = (((b[12] & 1) << 4) | (b[13] >> 4)) + 1
    total = ((b[13] & 0x0F) << 32) | int.from_bytes(b[14:18], "big")
    return sr, bps, total


def _wav_info(data: bytes):
    """fmt 块 → (采样率, 位深)。"""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    i = 12
    while i + 8 <= len(data):
        cid = data[i:i + 4]
        sz = int.from_bytes(data[i + 4:i + 8], "little")
        if cid == b"fmt " and i + 24 <= len(data):
            sr = int.from_bytes(data[i + 12:i + 16], "little")
            bits = int.from_bytes(data[i + 22:i + 24], "little")
            return sr, bits, None
        i += 8 + sz + (sz & 1)
        if sz == 0:
            break
    return None


_MP3_SR = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}
_MP3_BR = {3: (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0),
           2: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)}


def _mp3_info(data: bytes):
    """首帧头 → (采样率, None, 比特率 kbps)。"""
    i = 0
    if data[:3] == b"ID3":
        i = 10 + ((data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9])
    end = min(len(data), i + 8192)
    while i < end - 4:
        if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
            ver = (data[i + 1] >> 3) & 0x03
            layer = (data[i + 1] >> 1) & 0x03
            sri = (data[i + 2] >> 2) & 0x03
            bri = (data[i + 2] >> 4) & 0x0F
            if ver in _MP3_SR and sri != 3 and layer == 1 and bri:
                return _MP3_SR[ver][sri], None, _MP3_BR[3 if ver == 3 else 2][bri]
        i += 1
    return None


def _audio_info(path: str, duration_ms) -> dict:
    """歌曲信息四值（含单位），解析不了的位置用 —。结果按文件路径缓存。"""
    key = path or ""
    hit = _AUDIO_INFO_CACHE.get(key)
    if hit is not None:
        return hit
    ext = os.path.splitext(key)[1].lower()
    fmt = _FMT_NAMES.get(ext, ext[1:].upper() if ext.startswith(".") and len(ext) > 1 else "—")
    sr = bits = total = None
    size_ok = bool(key) and os.path.isfile(key)
    if size_ok:
        try:
            with open(key, "rb") as f:
                head = f.read(65536)
            parsed = {"flac": _flac_info, "wav": _wav_info}.get(ext[1:])
            if parsed:
                sr, bits, total = parsed(head) or (None, None, None)
            elif ext == ".mp3":
                sr, bits, _br = _mp3_info(head) or (None, None, None)
        except OSError:
            pass
    br = None
    if size_ok and duration_ms:
        try:  # 平均比特率=文件大小×8/时长，对 CBR/VBR/FLAC 都成立
            br = round(os.path.getsize(key) * 8 / (duration_ms / 1000) / 1000)
        except OSError:
            br = None
    vals = {
        "format": fmt or "—",
        "samplerate": (f"{sr / 1000:g} kHz" if sr else "—"),
        "bitrate": (f"{br} kbps" if br else "—"),
        "bits": (f"{bits} bit" if bits else "—"),
        "duration": (f"{(duration_ms or 0) // 60000}:{(duration_ms or 0) % 60000 // 1000:02d}"
                     if duration_ms else "—"),
    }
    if len(_AUDIO_INFO_CACHE) > 4:
        _AUDIO_INFO_CACHE.clear()
    _AUDIO_INFO_CACHE[key] = vals
    return vals


def _format_info(cfg: dict, meta: dict) -> str:
    """按 info_template 渲染歌曲信息行；四值全未知时返回空串（整行隐藏）。"""
    vals = _audio_info(meta.get("filename") or "", meta.get("duration_ms"))
    out = str(cfg.get("info_template", "{format} {samplerate} {bitrate} {bits}"))
    for k, v in vals.items():
        out = out.replace("{" + k + "}", v)
    out = re.sub(r"\{[a-z_]+\}", "", out)  # 未识别 token 直接剥掉
    out = re.sub(r"\s+", " ", out).strip()
    if out in ("", "—", "— — — —"):
        return ""
    return out


def _anchor_cx(anchor: str, cx: int, slot_w: int, cw: int) -> int:
    """封面缩放基准 → 封面左缘 x。

    left=左缘钉在 cx；right=右缘钉在槽位右端（cx+slot_w）；center=槽位居中向两边伸展；
    center_bound=同 center，但左缘一旦到边线（cx）即停、增长只向右。
    """
    if anchor == "right":
        return cx + slot_w - cw
    if anchor in ("center", "center_bound"):
        x = cx + (slot_w - cw) // 2
        return max(cx, x) if anchor == "center_bound" else x
    return cx


def render_poster(cover_bytes: bytes | None, meta: dict, w: int, h: int, cfg: dict,
                  want_anchor: bool = False, bg: Image.Image | None = None, paused: bool = False):
    """渲染海报。want_anchor=True 时返回 (img, anchor)，anchor=(文字区左缘x, 专辑行底部y)。

    bg 可传入缓存的模糊背景（RGBA，会被 copy 后使用）；cover 为 None 时背景由 bg 决定仍适用。
    paused=True 时按 pause_mode 压暗/画「已暂停」角标。
    """
    cover = _open_cover(cover_bytes)

    if bg is None:
        bg = _blur_bg(cover, w, h, cfg).convert("RGBA")
    else:
        bg = bg.copy()

    # 暂停反馈（范围可选）：darken=仅背景在此压暗；all=整幅在合成完后再压（见文末）
    _pause_on = paused and cfg.get("pause_mode") in ("darken", "both")
    _pct = max(0, min(95, int(cfg.get("pause_darken", 30) or 0)))
    _scope = cfg.get("pause_darken_scope", "all")
    if _pause_on and _pct and _scope == "bg":
        bg.alpha_composite(Image.new("RGBA", bg.size, (0, 0, 0, _pct * 255 // 100)))

    # 前景清晰封面：保持原分辨率 1:1（绝不放大），超屏才等比缩小；不裁剪、不拉伸
    dim = min(w, h)  # 几何比例基准：取宽高较小者（横屏=h 不变；竖屏=w 自适应）
    cx = int(dim * cfg["cover_margin_ratio"]) + int(cfg.get("cover_offset_x", 0) or 0)
    max_h = int(dim * 0.82)
    max_w = int(w * 0.52)
    anchor = cfg.get("cover_anchor", "left")  # 缩放基准：left=左缘固定（向右伸缩）/
    # right=右缘固定（向左伸缩，文字区恒定）/ center=槽位居中向两边伸展 /
    # center_bound=居中伸展但左缘到边线即停、只向右
    if cover is not None:
        iw, ih = cover.size
        fit = min(1.0, max_h / ih, max_w / iw)
        user_scale = max(0.3, min(2.0, float(cfg.get("cover_scale", 1.0) or 1.0)))
        if _pause_on and cfg.get("pause_shrink"):
            # 暂停时封面缩小（可选效果）：在用户倍率基础上再乘 (1 - 幅度%)
            shrink = max(0, min(50, int(cfg.get("pause_shrink_pct", 8) or 0))) / 100.0
            user_scale *= max(0.3, 1.0 - shrink)
        scale = fit * user_scale
        if abs(scale - 1.0) > 1e-3:
            cover = cover.resize((max(1, int(iw * scale)), max(1, int(ih * scale))), Image.LANCZOS)
        cw, ch = cover.size
        cy = (h - ch) // 2 + int(cfg.get("cover_offset_y", 0) or 0)
        cover_x = _anchor_cx(anchor, cx, max_w, cw)
        rad = int(cfg.get("cover_radius", 0) or 0)
        if rad <= 0:  # 0=自动：沿用写死时代的短边/60
            rad = max(6, min(cw, ch) // 60)
        fg = cover.convert("RGBA")
        fg = _rounded(fg, rad)
        sa = max(0, min(255, int(cfg.get("cover_shadow_alpha", 130) or 0)))
        if sa:  # 投影在小尺寸上生成再放大（高斯很贵，1/3 尺寸视觉等效）
            so = max(4, int(cfg.get("cover_shadow_offset", 40) or 40))
            k = 3
            sw2, sh2 = max(8, (cw + 2 * so) // k), max(8, (ch + 2 * so) // k)
            shadow = Image.new("RGBA", (sw2, sh2), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).rounded_rectangle(
                [so // k, so // k, (cw + so) // k, (ch + so) // k],
                radius=max(2, rad // k), fill=(0, 0, 0, sa))
            shadow = shadow.filter(ImageFilter.GaussianBlur(18 / k))
            shadow = shadow.resize((cw + 2 * so, ch + 2 * so), Image.BILINEAR)
            bg.alpha_composite(shadow, (cover_x - so, cy - so))
        csw = max(0, min(8, int(cfg.get("cover_stroke_w", 0) or 0)))
        if csw:  # 封面描边画在 fg 圆角边界上
            csrgb = _hex_rgb(cfg.get("cover_stroke_color"), (0, 0, 0))
            ImageDraw.Draw(fg).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=rad,
                                                 outline=(*csrgb, 255), width=csw)
        bg.alpha_composite(fg, (cover_x, cy))
    else:
        ch = int(int(h * cfg["cover_height_ratio"]) *
                 max(0.3, min(2.0, float(cfg.get("cover_scale", 1.0) or 1.0))))
        cw = ch
        cy = (h - ch) // 2 + int(cfg.get("cover_offset_y", 0) or 0)
        cover_x = _anchor_cx(anchor, cx, max_w, cw)
        d = ImageDraw.Draw(bg)
        d.rounded_rectangle([cover_x, cy, cover_x + cw, cy + ch], radius=max(8, ch // 60),
                            fill=(40, 44, 58, 255), outline=(90, 96, 120, 255), width=2)
        try:
            nf = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "seguisym.ttf"),
                                    ch // 8)
            d.text((cover_x + cw / 2, cy + ch / 2), "♪", font=nf, fill=(150, 158, 178, 255), anchor="mm")
        except OSError:
            pass

    # 右侧文字区（歌名/歌手/专辑三行各自独立样式：字号/字体/颜色/加粗/过长/阴影/描边）
    anchor = None
    if cfg["show_text"]:
        # 左缘基准：文字紧跟封面右缘（随封面尺寸移动）；右缘基准：文字固定在槽位右端
        tx = (cx + max_w if anchor == "right" else cover_x + cw) + int(dim * 0.055) \
            + int(cfg.get("text_offset_x", 0) or 0)
        tw_max = w - tx - int(w * 0.06)
        # 单行硬上限：从文字起点到屏幕右缘留 2% 边距（吸收超它就放弃，绝不出屏）
        line_limit = max(tw_max, w - tx - int(w * 0.02))
        if tw_max > w * 0.12:  # 门槛按宽度算（原按高度会把竖屏的窄文本区整个跳过）
            layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(layer)
            texts = {
                "title": meta.get("title") or "未知曲目",
                "artist": meta.get("artist") or "未知艺术家",
                "album": meta.get("album") or "",
                "info": _format_info(cfg, meta),  # 歌曲信息行（模板渲染，全未知则空=隐藏）
            }
            # 行顺序可调（line_order）：按配置顺序出图；未知键剔除、缺失键按默认序补尾
            known = ("title", "artist", "album", "info")
            order = [g for g in (cfg.get("line_order") or known) if g in known]
            for g in known:
                if g not in order:
                    order.append(g)
            blocks = []  # (组名, 折行后各行, 字体, 字色RGB, 阴影, 描边宽, 描边色RGB)
            for g in order:
                if not cfg.get(f"{g}_show", True):
                    continue  # 逐行显示开关
                text = texts[g]
                if not text:
                    continue
                bold = bool(cfg.get(f"{g}_bold", g == "title"))
                font, real_bold = _load_font(
                    bold, int(dim * float(cfg.get(f"{g}_size_ratio", 0.042) or 0.042)),
                    cfg.get(f"{g}_font_file"))
                # 描边：用户设置的宽度优先；未设时走加粗降级链兜底（真实粗体无需描边，
                # 重描边会把宋体类细横画肿掉，故兜底只有 1px）
                sw = max(0, min(6, int(cfg.get(f"{g}_stroke_w", 0) or 0)))
                if sw == 0 and bold and not real_bold:
                    sw = 1
                overflow = cfg.get(f"{g}_overflow", "wrap" if g == "title" else "ellipsis")
                if overflow == "wrap":  # 折行最多 4 行，无省略号（超限截断）
                    lines = _wrap_title(
                        draw, text, font, tw_max, 4,
                        max(0, min(20, int(cfg.get(f"{g}_space_window", 0) or 0))),
                        bool(cfg.get(f"{g}_bracket_break", True)), line_limit)
                else:
                    lines = [_ellipsis(draw, text, font, tw_max)]
                blocks.append((g, lines, font, _hex_rgb(cfg.get(f"{g}_color"), (255, 255, 255)),
                               bool(cfg.get(f"{g}_shadow", True)), sw,
                               _hex_rgb(cfg.get(f"{g}_stroke_color"), (0, 0, 0))))
            t_gap = int(dim * cfg.get("title_line_gap_ratio", 0.012))   # 歌名折行间距
            sub_gap = int(dim * cfg.get("sub_line_gap_ratio", 0.014))   # 歌手/专辑折行与行间
            t_sub_gap = int(dim * cfg.get("title_sub_gap_ratio", 0.02))  # 歌名与副行间距

            def _intra(g):
                return t_gap if g == "title" else sub_gap

            # 行间距语义：歌名行之后用 title_sub_gap（随行顺序走），其余行间用 sub_gap
            block_h = 0
            prev_g = None
            for g, lines, font, *_rest in blocks:
                if prev_g is not None:
                    block_h += t_sub_gap if prev_g == "title" else sub_gap
                block_h += font.size * len(lines) + _intra(g) * (len(lines) - 1)
                prev_g = g
            dy = int(cfg.get("text_offset_y", 0) or 0)
            valign = cfg.get("text_valign", "center")
            if valign == "top":
                ty = cy + dy
            elif valign == "bottom":
                ty = cy + ch - block_h + dy
            else:
                ty = cy + (ch - block_h) // 2 + dy
            align = cfg.get("text_align", "left")
            if align == "center":
                draw_x, draw_anchor = tx + tw_max // 2, "ma"
            elif align == "right":
                draw_x, draw_anchor = tx + tw_max, "ra"
            else:
                draw_x, draw_anchor = tx, "la"
            prev_g = None
            for g, lines, font, fill, shadow, sw, srgb in blocks:
                if prev_g is not None:
                    ty += t_sub_gap if prev_g == "title" else sub_gap
                for ln in lines:
                    _draw_shadow_text(layer, (draw_x, ty), ln, font, fill=(*fill, 255),
                                      anchor=draw_anchor, shadow=shadow, stroke_width=sw,
                                      stroke_fill=(*srgb, 255) if sw else None)
                    ty += font.size + _intra(g)
                prev_g = g
            anchor = (tx, ty - _intra(blocks[-1][0])) if blocks else None  # 末行文字底部（全隐藏时无锚点）
            bg.alpha_composite(layer)
    if _pause_on and _pct and _scope == "all":
        # 整幅压暗（封面+文字一起变暗，恢复播放即还原）；仅背景模式已在开头压过
        bg.alpha_composite(Image.new("RGBA", bg.size, (0, 0, 0, _pct * 255 // 100)))
    if paused and cfg.get("pause_mode") in ("badge", "both"):
        # 「已暂停」角标：屏幕右下角半透明圆角黑底白字（与 show_text 无关）
        d = ImageDraw.Draw(bg)
        px = int(dim * float(cfg.get("sub_size_ratio", 0.042) or 0.042))
        bfont, _ = _load_font(True, px, None)
        text = "已暂停"
        tw = _text_len(d, text, bfont)
        pad = max(10, px // 3)
        pill_w, pill_h = int(tw + pad * 2), int(px + pad)
        x1 = w - int(w * 0.04) - pill_w
        y1 = h - int(h * 0.05) - pill_h
        d.rounded_rectangle([x1, y1, x1 + pill_w, y1 + pill_h], radius=pill_h // 2,
                            fill=(0, 0, 0, 150))
        _draw_shadow_text(bg, (x1 + pill_w / 2, y1 + pill_h / 2), text, bfont,
                          fill=(255, 255, 255, 235), anchor="mm", shadow=False,
                          stroke_width=max(1, px // 24), stroke_fill=(0, 0, 0, 120))
    img = bg.convert("RGB")
    if want_anchor:
        return img, anchor
    return img


def _open_cover(cover_bytes: bytes | None) -> Image.Image | None:
    """按内容哈希缓存已解码封面（同专辑连播时跳过重复解码）。"""
    if not cover_bytes:
        return None
    key = hash(cover_bytes)
    im = _COVER_CACHE.get(key)
    if im is None:
        try:
            im = Image.open(io.BytesIO(cover_bytes))
            im.load()
        except OSError:
            im = None
        if len(_COVER_CACHE) > 2:
            _COVER_CACHE.clear()
        _COVER_CACHE[key] = im
    return im


_COVER_CACHE: dict = {}
_BG_CACHE: dict = {}


def _get_bg(cover_bytes: bytes | None, w: int, h: int, cfg: dict) -> Image.Image:
    """缓存的模糊背景（RGBA 原件，调用方 copy 后使用）；同封面连播零重复模糊。"""
    key = (w, h, cfg.get("bg_style"), cfg.get("blur_type"), cfg.get("blur_radius"),
           cfg.get("darken"), _night_alpha(cfg), hash(cover_bytes or b""))
    bg = _BG_CACHE.get(key)
    if bg is None:
        bg = _blur_bg(_open_cover(cover_bytes), w, h, cfg).convert("RGBA")
        if len(_BG_CACHE) > 4:
            _BG_CACHE.clear()
        _BG_CACHE[key] = bg
    return bg


def render_and_apply(cover_bytes: bytes | None, meta: dict, cfg: dict, monitors: list[dict],
                     paused: bool = False) -> list[str]:
    """逐屏渲染并设置；PNG 输出避免 JPEG 压缩发虚（compress_level=1 提速编码）。
    首屏锚点（专辑行位置）写盘供可视化面板跟随。paused=按 pause_mode 叠加暂停反馈。"""
    out_dir = cfg["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    dw = _get_wallpaper_com()
    targets = _filter_monitors(monitors, cfg.get("monitors", "all"))
    paths = []
    anchor = None
    for i, m in enumerate(targets):
        bg = _get_bg(cover_bytes, m["w"], m["h"], cfg)
        img, anchor_i = render_poster(cover_bytes, meta, m["w"], m["h"], cfg,
                                      want_anchor=True, bg=bg, paused=paused)
        if i == 0:
            anchor = anchor_i
        path = os.path.join(out_dir, f"wallpaper_{m['w']}x{m['h']}.png")
        img.save(path, "PNG", optimize=False, compress_level=1)
        jpg = os.path.join(out_dir, f"wallpaper_{m['w']}x{m['h']}.jpg")
        if os.path.exists(jpg):
            try:
                os.remove(jpg)
            except OSError:
                pass
        paths.append(path)

    for m, path in zip(targets, paths):
        dw.SetWallpaper(m["id"], path)
    dw.SetPosition(DWPOS_FILL)
    # 可视化面板锚点：屏幕坐标（主屏文字区左缘、专辑行底部下方留一点空隙）
    if anchor and targets:
        m0 = targets[0]
        data = {"x": m0.get("left", 0) + anchor[0], "y": m0.get("top", 0) + anchor[1] + int(m0["h"] * 0.012)}
        try:
            with open(os.path.join(out_dir, "vis_anchor.json"), "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass
    return paths


def _filter_monitors(monitors: list[dict], which) -> list[dict]:
    if which == "all" or not which:
        return monitors
    if isinstance(which, str):
        which = [which]
    return [m for m in monitors if any(w in m["id"] for w in which)]


def capture_original(cfg: dict) -> None:
    """首次运行记录原壁纸（只记一次）。"""
    if cfg.get("original_wallpaper"):
        return
    try:
        dw = _get_wallpaper_com()
        mid = dw.GetMonitorDevicePathAt(0)
        if not mid:
            return
        cur = dw.GetWallpaper(mid)
        pos = dw.GetPosition()
        cfg["original_wallpaper"] = cur
        cfg["original_position"] = int(pos)
        config.save(cfg)
    except Exception:
        pass


def restore_original(cfg: dict) -> str:
    orig = cfg.get("original_wallpaper")
    if not orig or not os.path.exists(orig):
        return f"config 里没有可恢复的原壁纸记录（{orig!r}），请手动在 设置→个性化 里改回"
    dw = _get_wallpaper_com()
    dw.SetWallpaper(None, orig)
    dw.SetPosition(cfg.get("original_position") if cfg.get("original_position") is not None else DWPOS_FILL)
    return f"已恢复原壁纸：{orig}"
