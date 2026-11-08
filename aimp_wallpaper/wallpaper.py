"""海报式壁纸渲染 + 多屏设置。

布局（用户选定）：背景=封面放大铺满+高斯模糊+压暗；前景=清晰封面偏左，右侧歌名/歌手—专辑。
设置壁纸用 comtypes 手写 COM 接口 IDesktopWallpaper，逐显示器 SetWallpaper + DWPOS_FILL。
"""
from __future__ import annotations

import io
import json
import os
import numpy as np
import re

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
    """[{id, w, h, left, top}]，物理像素（进程已声明 per-monitor DPI aware）。"""
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
        except OSError:
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
    for name in (("msyhbd.ttc", "msyh.ttc") if bold else ("msyh.ttc", "msyhbd.ttc")):
        try:
            return ImageFont.truetype(os.path.join(fonts_dir, name), size), bold
        except OSError:
            continue
    return ImageFont.load_default(size), False


def _cover_fit_full(im: Image.Image, w: int, h: int) -> Image.Image:
    """等比放大铺满再居中裁剪（全分辨率 LANCZOS）。"""
    im = im.convert("RGB")
    scale = max(w / im.width, h / im.height)
    im = im.resize((max(w, int(im.width * scale + 0.5)), max(h, int(im.height * scale + 0.5))), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _placeholder_bg(w: int, h: int) -> Image.Image:
    bg = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(bg)
    top, bottom = (34, 40, 54), (16, 18, 26)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return bg


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


def _blur_bg(cover: Image.Image | None, w: int, h: int, cfg: dict) -> Image.Image:
    """背景方案分发：blur=高斯模糊 / blur_vignette=模糊+暗角 / sharp=原图铺满 / gradient=主色渐变。"""
    style = cfg.get("bg_style", "blur")
    if cover is None:
        return _placeholder_bg(w, h)
    if style == "sharp":
        bg = _cover_fit_full(cover, w, h)
        return ImageEnhance.Brightness(bg).enhance(cfg["darken"])
    if style == "gradient":
        base = _dominant_color(cover)
        k = float(cfg["darken"])
        top = tuple(int(c * 0.30 * k / max(0.75, k)) for c in base)
        bottom = tuple(min(255, int(c * 0.75 * max(0.75, k))) for c in base)
        bg = Image.new("RGB", (w, h))
        d = ImageDraw.Draw(bg)
        for y in range(h):
            t = y / max(1, h - 1)
            d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
        return bg
    # blur / blur_vignette：1/3 降采样 + 高斯（双线性足够，~10x 提速）
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
    if style == "blur_vignette":
        bg = _vignette(bg, 120)
    return bg


def _ellipsis(draw, text, font, max_w):
    """单行省略号截断。"""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return (text + "…") if text else "…"


def _wrap_title(draw, text, font, max_w, max_lines=2):
    """超宽处理：max_lines>1 按像素宽度折行（末行放不下收省略号）；==1 直接省略号截断。"""
    if max_lines <= 1:
        return [_ellipsis(draw, text, font, max_w)]
    if draw.textlength(text, font=font) <= max_w:
        return [text]
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > max_w and cur:
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
    d = ImageDraw.Draw(layer)
    x, y = xy
    off = max(2, font.size // 24)
    if shadow:
        d.text((x + off, y + off), text, font=font, fill=(0, 0, 0, shadow_alpha), anchor=anchor,
               stroke_width=stroke_width)
    d.text((x, y), text, font=font, fill=fill, anchor=anchor, stroke_width=stroke_width)


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
    cx = int(h * cfg["cover_margin_ratio"])
    if cover is not None:
        iw, ih = cover.size
        max_h = int(h * 0.82)
        max_w = int(w * 0.52)
        scale = min(1.0, max_h / ih, max_w / iw)
        if scale < 1.0:
            cover = cover.resize((max(1, int(iw * scale)), max(1, int(ih * scale))), Image.LANCZOS)
        cw, ch = cover.size
        cy = (h - ch) // 2
        fg = cover.convert("RGBA")
        fg = _rounded(fg, max(6, min(cw, ch) // 60))
        shadow = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([40, 40, cw + 40, ch + 40], radius=max(6, min(cw, ch) // 60),
                                                 fill=(0, 0, 0, 130))
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))
        bg.alpha_composite(shadow, (cx - 40, cy - 40))
        bg.alpha_composite(fg, (cx, cy))
    else:
        ch = int(h * cfg["cover_height_ratio"])
        cw = ch
        cy = (h - ch) // 2
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
        tx = cx + cw + int(h * 0.055)
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
            sub_entries = [artist] + ([album] if album and album != artist else [])
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
            ty = cy + (ch - (th + block_gap + sh)) // 2
            tr, tg, tb = _hex_rgb(cfg.get("title_color"), (255, 255, 255))
            sr, sg, sb = _hex_rgb(cfg.get("sub_color"), (255, 255, 255))
            for ln in lines:
                _draw_shadow_text(layer, (tx, ty), ln, title_font, fill=(tr, tg, tb, 255),
                                  stroke_width=title_stroke, shadow=shadow)
                ty += title_font.size + line_gap
            ty += block_gap
            for s in sub_lines:
                _draw_shadow_text(layer, (tx, ty), s, sub_font, fill=(sr, sg, sb, 255),
                                  stroke_width=sub_stroke, shadow=shadow)
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
    for i, m in enumerate(targets):
        bg = _get_bg(cover_bytes, m["w"], m["h"], cfg)
        img, anchor_i = render_poster(cover_bytes, meta, m["w"], m["h"], cfg,
                                      want_anchor=True, bg=bg)
        if i == 0:
            anchor = anchor_i
        path = os.path.join(out_dir, f"wallpaper_{m['w']}x{m['h']}.png")
        img.save(path, "PNG", optimize=False, compress_level=1)
        dw.SetWallpaper(m["id"], path)
        jpg = os.path.join(out_dir, f"wallpaper_{m['w']}x{m['h']}.jpg")
        if os.path.exists(jpg):
            try:
                os.remove(jpg)
            except OSError:
                pass
        paths.append(path)
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
