"""海报式壁纸渲染 + 多屏设置。

布局（用户选定）：背景=封面放大铺满+高斯模糊+压暗；前景=清晰封面偏左，右侧歌名/歌手—专辑。
设置壁纸用 comtypes 手写 COM 接口 IDesktopWallpaper，逐显示器 SetWallpaper + DWPOS_FILL。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time

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


def get_monitors() -> list[dict]:
    """[{id, w, h, left, top}]，物理像素（进程已声明 per-monitor DPI aware）。

    系统会登记已断开的显示器（如合盖外接时的笔记本屏），对它 GetMonitorRECT 抛
    COMError(E_FAIL)，而 COMError 不是 OSError 子类——必须宽捕，否则单块屏失败
    会让整次渲染崩掉（2026-11-09 壁纸不更新的真因）。
    """
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
    return monitors


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


def _blur_bg(cover: Image.Image | None, w: int, h: int, cfg: dict) -> Image.Image:
    if cover is not None:
        # 全是模糊，双线性足够；直接在 1/3 尺寸上等比铺满裁剪+模糊再放大（~10x 提速，视觉无差）
        sw, sh = max(2, w // 3), max(2, h // 3)
        im = cover.convert("RGB")
        scale = max(sw / im.width, sh / im.height)
        im = im.resize((max(sw, int(im.width * scale + 0.5)), max(sh, int(im.height * scale + 0.5))), Image.BILINEAR)
        x, y = (im.width - sw) // 2, (im.height - sh) // 2
        bg = im.crop((x, y, x + sw, y + sh))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=max(4, cfg["blur_radius"]) / 3.0))
        bg = bg.resize((w, h), Image.BILINEAR)
        bg = ImageEnhance.Brightness(bg).enhance(cfg["darken"])
        bg = ImageEnhance.Color(bg).enhance(0.9)
    else:
        bg = Image.new("RGB", (w, h))
        d = ImageDraw.Draw(bg)
        top, bottom = (34, 40, 54), (16, 18, 26)
        for y in range(h):
            t = y / max(1, h - 1)
            d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
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
               stroke_width: int = 0, base_ascent: int = 0):
    """按 anchor（'la'/'ma'/'ra'）绘制多字体文本；非首段按 ascent 差对齐基线。"""
    widths = [d.textlength(t, font=f) for t, f in runs]
    total = sum(widths)
    start = x - total / 2 if anchor.startswith("m") else (x - total if anchor.startswith("r") else x)
    cur = start
    for (t, f), w in zip(runs, widths):
        dy = base_ascent - f.getmetrics()[0]
        d.text((cur, y + dy), t, font=f, fill=fill, anchor="l" + anchor[1],
               stroke_width=stroke_width,
               stroke_fill=fill if stroke_width else None)
        cur += w


def _ellipsis(draw, text, font, max_w):
    """单行省略号截断（宽度按字体回退后的实际宽度算）。"""
    if _text_len(draw, text, font) <= max_w:
        return text
    while text and _text_len(draw, text + "…", font) > max_w:
        text = text[:-1]
    return (text + "…") if text else "…"


def _wrap_title(draw, text, font, max_w, max_lines=2):
    """超宽处理：max_lines>1 按像素宽度折行（末行放不下收省略号）；==1 直接省略号截断。"""
    if max_lines <= 1:
        return [_ellipsis(draw, text, font, max_w)]
    if _text_len(draw, text, font) <= max_w:
        return [text]
    lines, cur = [], ""
    for ch in text:
        if _text_len(draw, cur + ch, font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
        if len(lines) == max_lines:
            break
    if len(lines) == max_lines:  # 装不下：末行收省略号
        rest = cur + text[text.index(cur) + len(cur):] if cur and text.find(cur) >= 0 else cur
        lines[-1] = _ellipsis(draw, rest.rstrip(), font, max_w)
    elif cur:
        lines.append(cur)
    return lines


def _draw_shadow_text(layer, xy, text, font, fill=(255, 255, 255, 255), anchor="la",
                      shadow_alpha=140, stroke_width=0, shadow=True):
    """逐字符字体回退后再绘制（避免缺字形画方框）。"""
    d = ImageDraw.Draw(layer)
    x, y = xy
    off = max(2, font.size // 24)
    runs = _text_runs(text, font)
    if not runs:
        return
    ascent = font.getmetrics()[0]
    if shadow:
        _draw_runs(d, x + off, y + off, runs, (0, 0, 0, shadow_alpha), anchor,
                   stroke_width=stroke_width, base_ascent=ascent)
    _draw_runs(d, x, y, runs, fill, anchor, stroke_width=stroke_width, base_ascent=ascent)


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


def render_poster(cover_bytes: bytes | None, meta: dict, w: int, h: int, cfg: dict,
                  want_anchor: bool = False, bg: Image.Image | None = None):
    """渲染海报。want_anchor=True 时返回 (img, anchor)，anchor=(文字区左缘x, 专辑行底部y)。

    bg 可传入缓存的模糊背景（RGBA，会被 copy 后使用）；cover 为 None 时背景由 bg 决定仍适用。
    """
    cover = _open_cover(cover_bytes)

    if bg is None:
        bg = _blur_bg(cover, w, h, cfg).convert("RGBA")
    else:
        bg = bg.copy()

    # 前景清晰封面：保持原分辨率 1:1（绝不放大），超屏才等比缩小；不裁剪、不拉伸
    cx = int(h * cfg["cover_margin_ratio"]) + int(cfg.get("cover_offset_x", 0) or 0)
    if cover is not None:
        iw, ih = cover.size
        max_h = int(h * 0.82)
        max_w = int(w * 0.52)
        fit = min(1.0, max_h / ih, max_w / iw)
        user_scale = max(0.3, min(2.0, float(cfg.get("cover_scale", 1.0) or 1.0)))
        scale = fit * user_scale
        if abs(scale - 1.0) > 1e-3:
            cover = cover.resize((max(1, int(iw * scale)), max(1, int(ih * scale))), Image.LANCZOS)
        cw, ch = cover.size
        cy = (h - ch) // 2 + int(cfg.get("cover_offset_y", 0) or 0)
        fg = cover.convert("RGBA")
        fg = _rounded(fg, max(6, min(cw, ch) // 60))
        shadow = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([40, 40, cw + 40, ch + 40], radius=max(6, min(cw, ch) // 60),
                                                 fill=(0, 0, 0, 130))
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))
        bg.alpha_composite(shadow, (cx - 40, cy - 40))
        bg.alpha_composite(fg, (cx, cy))
    else:
        ch = int(int(h * cfg["cover_height_ratio"]) *
                 max(0.3, min(2.0, float(cfg.get("cover_scale", 1.0) or 1.0))))
        cw = ch
        cy = (h - ch) // 2 + int(cfg.get("cover_offset_y", 0) or 0)
        d = ImageDraw.Draw(bg)
        d.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=max(8, ch // 60),
                            fill=(40, 44, 58, 255), outline=(90, 96, 120, 255), width=2)
        try:
            nf = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "seguisym.ttf"),
                                    ch // 8)
            d.text((cx + cw / 2, cy + ch / 2), "♪", font=nf, fill=(150, 158, 178, 255), anchor="mm")
        except OSError:
            pass

    # 右侧文字区
    anchor = None
    if cfg["show_text"]:
        tx = cx + cw + int(h * 0.055) + int(cfg.get("text_offset_x", 0) or 0)
        tw_max = w - tx - int(w * 0.06)
        if tw_max > h * 0.15:
            layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            title_font_file = cfg.get("title_font_file")
            sub_font_file = cfg.get("sub_font_file")
            title_bold = bool(cfg.get("title_bold", True))
            sub_bold = bool(cfg.get("sub_bold", False))
            shadow = bool(cfg.get("text_shadow", True))
            title_font, title_real = _load_font(title_bold, int(h * cfg["title_size_ratio"]), title_font_file)
            sub_font, sub_real = _load_font(sub_bold, int(h * cfg["sub_size_ratio"]), sub_font_file)
            # 加粗降级链：真实粗体字面/可变字体实例 → 无则 1px 轻描边（重描边会把宋体类细横画肿掉）
            title_stroke = 1 if (title_bold and not title_real) else 0
            sub_stroke = 1 if (sub_bold and not sub_real) else 0
            title = meta.get("title") or "未知曲目"
            lines = _wrap_title(ImageDraw.Draw(layer), title, title_font, tw_max,
                                1 if cfg.get("title_overflow", "wrap") == "ellipsis" else 2)
            artist = meta.get("artist") or "未知艺术家"
            album = meta.get("album") or ""
            # 歌手/专辑同名也各占一行（此前同名被当重复吞掉，用户报为 bug）
            sub_entries = [artist] + ([album] if album else [])
            sub_draw = ImageDraw.Draw(layer)
            sub_wrap = cfg.get("sub_overflow", "ellipsis") == "wrap"
            sub_lines = []
            for s in sub_entries:
                if sub_wrap:  # 折行（每条最多 2 行，末行省略号）
                    sub_lines.extend(_wrap_title(sub_draw, s, sub_font, tw_max, 2))
                else:         # 省略号截断
                    sub_lines.append(_ellipsis(sub_draw, s, sub_font, tw_max))
            line_gap = int(h * cfg.get("title_line_gap_ratio", 0.012))
            sub_gap = int(h * cfg.get("sub_line_gap_ratio", 0.014))
            block_gap = int(h * cfg.get("title_sub_gap_ratio", 0.02))
            th = title_font.size * len(lines) + line_gap * (len(lines) - 1)
            sh = sub_font.size * len(sub_lines) + sub_gap * (len(sub_lines) - 1)
            block_h = th + block_gap + sh
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
            tr, tg, tb = _hex_rgb(cfg.get("title_color"), (255, 255, 255))
            sr, sg, sb = _hex_rgb(cfg.get("sub_color"), (255, 255, 255))
            for ln in lines:
                _draw_shadow_text(layer, (draw_x, ty), ln, title_font, fill=(tr, tg, tb, 255),
                                  stroke_width=title_stroke, shadow=shadow, anchor=draw_anchor)
                ty += title_font.size + line_gap
            ty += block_gap
            for s in sub_lines:
                _draw_shadow_text(layer, (draw_x, ty), s, sub_font, fill=(sr, sg, sb, 255),
                                  stroke_width=sub_stroke, shadow=shadow, anchor=draw_anchor)
                ty += sub_font.size + sub_gap
            anchor = (tx, ty - sub_gap)  # 专辑行文字底部
            bg.alpha_composite(layer)
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
    key = (w, h, cfg.get("blur_radius"), cfg.get("darken"), hash(cover_bytes or b""))
    bg = _BG_CACHE.get(key)
    if bg is None:
        bg = _blur_bg(_open_cover(cover_bytes), w, h, cfg).convert("RGBA")
        if len(_BG_CACHE) > 4:
            _BG_CACHE.clear()
        _BG_CACHE[key] = bg
    return bg


def render_and_apply(cover_bytes: bytes | None, meta: dict, cfg: dict, monitors: list[dict]) -> list[str]:
    """逐屏渲染并设置；PNG 输出避免 JPEG 压缩发虚（compress_level=1 提速编码）。
    首屏锚点（专辑行位置）写盘供可视化面板跟随。"""
    out_dir = cfg["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    dw = _get_wallpaper_com()
    targets = _filter_monitors(monitors, cfg.get("monitors", "all"))
    paths = []
    anchor = None
    layers = []          # 新图（供失败回退用）
    for i, m in enumerate(targets):
        bg = _get_bg(cover_bytes, m["w"], m["h"], cfg)
        img, anchor_i = render_poster(cover_bytes, meta, m["w"], m["h"], cfg,
                                      want_anchor=True, bg=bg)
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
        layers.append((m.get("left", 0), m.get("top", 0), m["w"], m["h"], img))

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
