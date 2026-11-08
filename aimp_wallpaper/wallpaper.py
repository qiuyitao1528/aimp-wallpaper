"""海报式壁纸渲染 + 多屏设置。

布局（用户选定）：背景=封面放大铺满+高斯模糊+压暗；前景=清晰封面偏左，右侧歌名/歌手—专辑。
设置壁纸用 comtypes 手写 COM 接口 IDesktopWallpaper，逐显示器 SetWallpaper + DWPOS_FILL。
"""
from __future__ import annotations

import io
import json
import os

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


def _load_font(bold: bool, size: int, font_file: str | None = None) -> ImageFont.FreeTypeFont:
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    if font_file:  # 用户指定字体（标题用描边加粗）
        try:
            return ImageFont.truetype(os.path.join(fonts_dir, font_file), size)
        except OSError:
            pass
    for name in (("msyhbd.ttc", "msyh.ttc") if bold else ("msyh.ttc", "msyhbd.ttc")):
        try:
            return ImageFont.truetype(os.path.join(fonts_dir, name), size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _cover_fit(im: Image.Image, w: int, h: int) -> Image.Image:
    """等比放大铺满再居中裁剪。"""
    im = im.convert("RGB")
    scale = max(w / im.width, h / im.height)
    im = im.resize((max(w, int(im.width * scale + 0.5)), max(h, int(im.height * scale + 0.5))), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


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


def _wrap_title(draw, text, font, max_w):
    """按像素宽度折行，最多 2 行，超出加省略号。"""
    if draw.textlength(text, font=font) <= max_w:
        return [text]
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
        if len(lines) == 2:
            break
    if len(lines) == 2:  # 装不下：第二行收省略号
        rest = cur + text[text.index(cur) + len(cur):] if cur and text.find(cur) >= 0 else cur
        last = rest.rstrip()
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last[:-1]
        lines[1] = (last + "…") if last else "…"
    elif cur:
        lines.append(cur)
    return lines


def _draw_shadow_text(layer, xy, text, font, fill=(255, 255, 255, 255), anchor="la",
                      shadow_alpha=140, stroke_width=0, shadow=True, bold_extra=0):
    d = ImageDraw.Draw(layer)
    x, y = xy
    off = max(2, font.size // 24)
    if shadow:
        d.text((x + off, y + off), text, font=font, fill=(0, 0, 0, shadow_alpha), anchor=anchor,
               stroke_width=stroke_width)
    d.text((x, y), text, font=font, fill=fill, anchor=anchor,
           stroke_width=stroke_width + bold_extra,
           stroke_fill=fill if bold_extra else None)


def _rounded(im: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=radius, fill=255)
    im = im.convert("RGBA")
    im.putalpha(mask)
    return im


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
            title_font = _load_font(title_bold, int(h * cfg["title_size_ratio"]), title_font_file)
            sub_font = _load_font(sub_bold, int(h * cfg["sub_size_ratio"]), sub_font_file)
            # 加粗实现：默认字体走真实粗体字面；自定义字体用同色描边模拟
            title_stroke = 1 if (title_bold and not title_font_file) else 0
            title_bold_extra = 2 if (title_bold and title_font_file) else 0
            sub_bold_extra = 2 if (sub_bold and sub_font_file) else 0
            title = meta.get("title") or "未知曲目"
            lines = _wrap_title(ImageDraw.Draw(layer), title, title_font, tw_max)
            artist = meta.get("artist") or "未知艺术家"
            album = meta.get("album") or ""
            sub_lines = [artist] + ([album] if album and album != artist else [])
            # 副行超宽截断
            sub_draw = ImageDraw.Draw(layer)
            for i, s in enumerate(sub_lines):
                while sub_draw.textlength(s, font=sub_font) > tw_max and len(s) > 4:
                    s = s[:-2].rstrip() + "…"
                sub_lines[i] = s
            line_gap = int(h * cfg.get("title_line_gap_ratio", 0.012))
            sub_gap = int(h * cfg.get("sub_line_gap_ratio", 0.014))
            block_gap = int(h * cfg.get("title_sub_gap_ratio", 0.02))
            th = title_font.size * len(lines) + line_gap * (len(lines) - 1)
            sh = sub_font.size * len(sub_lines) + sub_gap * (len(sub_lines) - 1)
            ty = cy + (ch - (th + block_gap + sh)) // 2
            for ln in lines:
                _draw_shadow_text(layer, (tx, ty), ln, title_font, stroke_width=title_stroke,
                                  shadow=shadow, bold_extra=title_bold_extra)
                ty += title_font.size + line_gap
            ty += block_gap
            for s in sub_lines:
                _draw_shadow_text(layer, (tx, ty), s, sub_font, fill=(235, 238, 245, 205),
                                  shadow=shadow, bold_extra=sub_bold_extra)
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
