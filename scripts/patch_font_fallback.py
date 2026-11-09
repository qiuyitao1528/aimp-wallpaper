# -*- coding: utf-8 -*-
"""逐字符字体回退：PIL 不会像 Windows 那样自动换字体，缺字形就画方框。
本补丁加入「主字体缺字形 → 依次尝试回退字体」的渲染与测量。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()

if "_FALLBACK_FONTS" in s:
    print("已打补丁，跳过")
    raise SystemExit

HELPERS = '''# ---------- 字体回退（PIL 不做系统级字体回退，缺字形会画方框） ----------

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
            notdef = _mask_sig(font, "\\uffff")
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
        fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\\Windows"), "Fonts")
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


'''

# 插到 _ellipsis 之前
s = s.replace("def _ellipsis(draw, text, font, max_w):", HELPERS + "def _ellipsis(draw, text, font, max_w):", 1)

# 测量改用 _text_len
s = s.replace('''def _ellipsis(draw, text, font, max_w):
    """单行省略号截断。"""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]''',
'''def _ellipsis(draw, text, font, max_w):
    """单行省略号截断（宽度按字体回退后的实际宽度算）。"""
    if _text_len(draw, text, font) <= max_w:
        return text
    while text and _text_len(draw, text + "…", font) > max_w:
        text = text[:-1]''')

s = s.replace('''    if draw.textlength(text, font=font) <= max_w:
        return [text]
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > max_w and cur:''',
'''    if _text_len(draw, text, font) <= max_w:
        return [text]
    lines, cur = [], ""
    for ch in text:
        if _text_len(draw, cur + ch, font) > max_w and cur:''')

# 副行超宽判断也走 _text_len（若存在）
s = s.replace("while sub_draw.textlength(s, font=sub_font) > tw_max and len(s) > 4:",
              "while _text_len(sub_draw, s, sub_font) > tw_max and len(s) > 4:")

# 绘制改用 runs
s = s.replace('''def _draw_shadow_text(layer, xy, text, font, fill=(255, 255, 255, 255), anchor="la",
                      shadow_alpha=140, stroke_width=0, shadow=True):
    d = ImageDraw.Draw(layer)
    x, y = xy
    off = max(2, font.size // 24)
    if shadow:
        d.text((x + off, y + off), text, font=font, fill=(0, 0, 0, shadow_alpha), anchor=anchor,
               stroke_width=stroke_width)
    d.text((x, y), text, font=font, fill=fill, anchor=anchor, stroke_width=stroke_width)''',
'''def _draw_shadow_text(layer, xy, text, font, fill=(255, 255, 255, 255), anchor="la",
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
    _draw_runs(d, x, y, runs, fill, anchor, stroke_width=stroke_width, base_ascent=ascent)''')

io.open(P, "w", encoding="utf-8").write(s)
print("已加入字体回退")
