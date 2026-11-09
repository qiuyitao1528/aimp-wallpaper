"""v0.2.1 新特性离线测试：背景四方案 / 日夜遮罩 / 每行样式 / 空格断行 / 配置迁移 / 设置窗存盘。

红线：全部用临时目录，不碰真实 config.json / output_dir；只输出 ASCII，不读渲染图进上下文。
运行：uv run python -I scripts/test_v021_features.py
"""
import io
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from aimp_wallpaper import config, wallpaper  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name} {detail}")
    if not cond:
        FAILS.append(name)


# ---------- A. 配置迁移 ----------
tmp = tempfile.mkdtemp(prefix="aw_test_")
old_cfg_path = os.path.join(tmp, "old", "config.json")
os.makedirs(os.path.dirname(old_cfg_path), exist_ok=True)
with open(old_cfg_path, "w", encoding="utf-8") as f:
    json.dump({"text_shadow": False, "sub_font_file": "simhei.ttf", "sub_bold": True,
               "sub_color": "#FF0000", "sub_overflow": "wrap", "sub_size_ratio": 0.03}, f)
config.CONFIG_PATH, _saved_path = old_cfg_path, config.CONFIG_PATH
cfg = config.load()
check("migrate artist_size", cfg["artist_size_ratio"] == 0.03)
check("migrate album_font", cfg["album_font_file"] == "simhei.ttf")
check("migrate artist_bold", cfg["artist_bold"] is True and cfg["album_bold"] is True)
check("migrate colors", cfg["artist_color"] == "#FF0000" and cfg["album_color"] == "#FF0000")
check("migrate overflow", cfg["artist_overflow"] == "wrap" and cfg["album_overflow"] == "wrap")
check("migrate shadows off", cfg["title_shadow"] is False and cfg["artist_shadow"] is False
      and cfg["album_shadow"] is False)

new_cfg_path = os.path.join(tmp, "new", "config.json")
os.makedirs(os.path.dirname(new_cfg_path), exist_ok=True)
with open(new_cfg_path, "w", encoding="utf-8") as f:
    json.dump({"artist_size_ratio": 0.09, "text_shadow": False}, f)
config.CONFIG_PATH = new_cfg_path
cfg = config.load()
check("new cfg untouched", cfg["artist_size_ratio"] == 0.09)
config.CONFIG_PATH = _saved_path

# ---------- B. 空格断行 ----------
fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
font = ImageFont.truetype(os.path.join(fonts_dir, "msyh.ttc"), 40)
draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))
text = "aaaa bb cc dd"
w1 = wallpaper._text_len(draw, "aaaa b", font)   # 自然断点前的宽度
w2 = wallpaper._text_len(draw, "aaaa bb", font)  # 多吞一个字符
max_w = (w1 + w2) / 2  # 让自然断点落在 bb 词中间（余下 "b cc dd"）
lines0 = wallpaper._wrap_title(draw, text, font, max_w, 2, space_window=0)
lines5 = wallpaper._wrap_title(draw, text, font, max_w, 2, space_window=2)
print("wrap window=0:", ascii(lines0))
print("wrap window=2:", ascii(lines5))
check("wrap natural mid-word", lines0[1].startswith("b"), ascii(lines0))
check("wrap space break", lines5[0] == "aaaa bb" and lines5[1] == "cc dd", ascii(lines5))
# 首行吸收空格后允许超宽：确认 lines5[0] 宽度确实超过 max_w
check("wrap overflow allowed", wallpaper._text_len(draw, lines5[0], font) > max_w)
# 无空格可吸收时行为退化为普通断行
lines_none = wallpaper._wrap_title(draw, "aaaaXXbbXXcc", font, max_w, 2, space_window=3)
check("wrap no-space fallback", len(lines_none) == 2, ascii(lines_none))
# 短文本不折行
check("wrap fits", wallpaper._wrap_title(draw, "hi", font, 10_000, 2, 5) == ["hi"])

# ---------- C. 渲染：四种背景方案 + 夜间遮罩 ----------
rng = np.random.default_rng(7)


def synth_cover() -> bytes:
    im = Image.new("RGB", (900, 900))
    d = ImageDraw.Draw(im)
    for y in range(900):
        d.line([(0, y), (900, y)], fill=(int(255 * y / 900), 80, 255 - int(120 * y / 900)))
    d.ellipse([250, 250, 650, 650], fill=(255, 220, 120))
    noise = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    im.paste(Image.fromarray(noise), (450, 450))       # 高频噪声块：区分 sharp/blur
    for gy in range(0, 12):                            # 棋盘格：另一个高频特征
        for gx in range(0, 12):
            if (gx + gy) % 2 == 0:
                d.rectangle([60 + gx * 20, 60 + gy * 20, 78 + gx * 20, 78 + gy * 20], fill=(20, 200, 90))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


cover = synth_cover()
cover_img = Image.open(io.BytesIO(cover))
meta = {"title": "Shape of You (Major Lazer Remix feat. KSI)", "artist": "Ed Sheeran", "album": "Divide Deluxe"}
W, H = 1920, 1080


def arr(img):
    return np.asarray(img, dtype=np.float64)


def hf(a):
    return float(np.abs(np.diff(a, axis=0)).mean())


means = {}
for style in ("blur", "blur_vignette", "sharp", "gradient"):
    cfg = dict(config.DEFAULTS)
    cfg.update(bg_style=style, blur_radius=100, darken=0.75, show_text=False,
               theme_night_follow=False)
    img = wallpaper.render_poster(cover, meta, W, H, cfg)
    a = arr(img)
    means[style] = a
    check(f"render {style} size", img.size == (W, H), f"mean={a.mean():.1f}")
check("vignette darker bottom", arr(img).mean() >= 0 and
      means["blur_vignette"][int(H * 0.85):].mean() < means["blur"][int(H * 0.85):].mean(),
      f"bottom {means['blur_vignette'][int(H * 0.85):].mean():.1f} vs {means['blur'][int(H * 0.85):].mean():.1f}")

# 纯背景直测（避开前景封面/文字干扰）：sharp 保留高频细节、gradient 无空间纹理
bg_cfg = dict(config.DEFAULTS)
bg_cfg.update(bg_style="blur", blur_radius=100, darken=0.75, theme_night_follow=False)
bg_blur = arr(wallpaper._blur_bg(cover_img, W, H, bg_cfg))
bg_cfg["bg_style"] = "sharp"
bg_sharp = arr(wallpaper._blur_bg(cover_img, W, H, bg_cfg))
bg_cfg["bg_style"] = "gradient"
bg_grad = arr(wallpaper._blur_bg(cover_img, W, H, bg_cfg))
check("sharp is detailed", hf(bg_sharp) > hf(bg_blur) * 1.5,
      f"hf sharp={hf(bg_sharp):.2f} blur={hf(bg_blur):.2f}")
def texture(a):  # 扣掉纵向色带后剩纯空间纹理（渐变应≈0）
    return hf(a - a.mean(axis=1, keepdims=True))
check("gradient uniform", texture(bg_grad) < max(0.02, texture(bg_blur) / 5),
      f"texture grad={texture(bg_grad):.4f} blur={texture(bg_blur):.4f}")
check("styles differ", means["blur"].mean() != means["sharp"].mean())

# 夜间遮罩：强制深色主题基线（缓存 2s 内生效）
wallpaper._DARK_CACHE = (time.monotonic(), True)
cfg_night = dict(config.DEFAULTS)
cfg_night.update(bg_style="blur", blur_radius=100, darken=0.75, show_text=False,
                 theme_night_follow=True, night_overlay=40)
img_night = wallpaper.render_poster(cover, meta, W, H, cfg_night)
check("night overlay darkens", arr(img_night).mean() < means["blur"].mean(),
      f"{arr(img_night).mean():.1f} vs {means['blur'].mean():.1f}")
check("night alpha calc", wallpaper._night_alpha(cfg_night) == 40 * 255 // 100)
wallpaper._DARK_CACHE = (time.monotonic(), False)
img_day2 = wallpaper.render_poster(cover, meta, W, H, cfg_night)
check("day no overlay", abs(arr(img_day2).mean() - means["blur"].mean()) < 0.5,
      f"{arr(img_day2).mean():.1f} vs {means['blur'].mean():.1f}")

# ---------- D. 每行样式 + 锚点 ----------
cfg_t = dict(config.DEFAULTS)
cfg_t.update(bg_style="blur", blur_radius=100, darken=0.75, show_text=True,
             title_stroke_w=3, title_stroke_color="#FF0000",
             artist_stroke_w=2, artist_stroke_color="#00FF00",
             album_stroke_w=0, title_shadow=True, artist_shadow=False, album_shadow=True,
             wrap_space_window=5)
img_txt = wallpaper.render_poster(cover, meta, W, H, cfg_t)
img_nottxt = wallpaper.render_poster(cover, meta, W, H, {**cfg_t, "show_text": False})
check("text drawn", img_txt.size == (W, H))
# want_anchor=True 应返回 (img, anchor) 元组且锚点在屏内
ret = wallpaper.render_poster(cover, meta, W, H, cfg_t, want_anchor=True)
ax, ay = ret[1]
check("anchor tuple", isinstance(ret, tuple) and 0 <= ax < W and 0 <= ay < H, f"anchor=({ax},{ay})")
d2 = (np.asarray(img_txt, dtype=np.float64) - np.asarray(img_nottxt, dtype=np.float64))
check("text pixels changed", (np.abs(d2) > 2).sum() > 5000, f"changed={int((np.abs(d2) > 2).sum())}")
img_stroke0 = wallpaper.render_poster(cover, meta, W, H, {**cfg_t, "title_stroke_w": 0,
                                                          "artist_stroke_w": 0})
d3 = np.abs(np.asarray(img_txt, dtype=np.float64) - np.asarray(img_stroke0, dtype=np.float64))
check("stroke visible", (d3 > 2).sum() > 500, f"changed={int((d3 > 2).sum())}")
# 无封面路径
img_nc = wallpaper.render_poster(None, meta, W, H, {**cfg_t, "bg_style": "sharp"})
check("no-cover render ok", img_nc.size == (W, H))

# ---------- E. 设置窗口离线跑一遍（存盘写临时配置） ----------
import tkinter as tk  # noqa: E402
config.CONFIG_PATH = os.path.join(tmp, "gui", "config.json")
os.makedirs(os.path.dirname(config.CONFIG_PATH), exist_ok=True)
root = tk.Tk()
root.withdraw()
gui_cfg = config.load()
from aimp_wallpaper.settings_gui import SettingsWindow  # noqa: E402
win = SettingsWindow(root, gui_cfg)
n_labels = len(win._line_vars)
check("gui line groups", n_labels == 3, f"groups={list(win._line_vars)}")
win._line_vars["title"]["stroke_w"].set("3")
win._line_vars["title"]["shadow"].set(False)
win._line_vars["album"]["font"].set("黑体")
win.bg_style_var.set("模糊+暗角")
win.night_var.set(True)
win.night_alpha_var.set("70")
win.space_wrap_var.set("8")
win._save()
root.destroy()
with open(config.CONFIG_PATH, encoding="utf-8") as f:
    saved = json.load(f)
check("gui save style", saved.get("bg_style") == "blur_vignette", saved.get("bg_style"))
check("gui save night", saved.get("theme_night_follow") is True and saved.get("night_overlay") == 70)
check("gui save stroke", saved.get("title_stroke_w") == 3 and saved.get("title_stroke_color"))
check("gui save shadow", saved.get("title_shadow") is False and saved.get("album_shadow") is True)
expected_font = win._label_to_file.get("黑体")
check("gui save album font", saved.get("album_font_file") == expected_font,
      f"saved={ascii(saved.get('album_font_file'))} expected={ascii(expected_font)}")
check("gui save space wrap", saved.get("wrap_space_window") == 8)
check("gui save ratio", abs(saved.get("artist_size_ratio", 0) - gui_cfg["artist_size_ratio"]) < 1e-6)

print()

# ---------- F. 自启动：只在勾选状态相对现状变化时才写 ----------
import aimp_wallpaper.settings_gui as sg  # noqa: E402

calls = []
sg.set_autostart = lambda enabled: calls.append(enabled) or True
state = {"exists": False}
sg.autostart_enabled = lambda: state["exists"]

root2 = tk.Tk()
root2.withdraw()


def save_with(checkbox: bool):
    w = SettingsWindow(root2, config.load())
    w.autostart_var.set(checkbox)
    w._save()
    txt = w.status.cget("text")
    w.win.destroy()
    return txt


save_with(False)
check("autostart no-op same state", calls == [], str(calls))
green = save_with(True)
check("autostart enable called", calls == [True], str(calls))
check("autostart green status", "已保存" in green, ascii(green))
state["exists"] = True
save_with(True)
check("autostart no-op already on", calls == [True], str(calls))
save_with(False)
check("autostart disable called", calls == [True, False], str(calls))
sg.set_autostart = lambda enabled: False
state["exists"] = False
red = save_with(True)
check("autostart fail status", "失败" in red, ascii(red))
root2.destroy()
sg.set_autostart = None  # 还原（脚本即将退出，仅防误用）
sg.autostart_enabled = None

print()

# ---------- G. 模糊类型：gauss/box/motion/zoom/pixel/median/glass/dof/spin ----------
BLUR_TYPES = ("gauss", "box", "motion", "zoom", "pixel", "median", "glass", "dof", "spin")
blurs = {}
for t in BLUR_TYPES:
    c = dict(config.DEFAULTS)
    c.update(bg_style="blur", blur_type=t, blur_radius=60, darken=0.75, theme_night_follow=False)
    t0 = time.monotonic()
    b = wallpaper._blur_bg(cover_img, W, H, c)
    ms = (time.monotonic() - t0) * 1000
    ab = arr(b)
    blurs[t] = ab
    check(f"blur_type {t} ok", b.size == (W, H), f"mean={ab.mean():.1f} {ms:.0f}ms")
    check(f"blur_type {t} fast", ms < 800, f"{ms:.0f}ms")
for t in ("box", "motion", "zoom", "pixel", "median", "glass", "dof", "spin"):
    d = float(np.abs(blurs[t] - blurs["gauss"]).mean())
    check(f"blur_type {t} differs from gauss", d > 0.2, f"meandiff={d:.2f}")
# 像素化应有块状结构（块内几乎零差异）
px = blurs["pixel"]
inner = px[100:164, 100:164]
check("pixel blocky", float(np.abs(np.diff(inner, axis=0)).mean()) < 1.0,
      f"inner hf={float(np.abs(np.diff(inner, axis=0)).mean()):.3f}")
# 玻璃：固定种子 → 两次渲染结果逐像素一致
cg = dict(config.DEFAULTS); cg.update(bg_style="blur", blur_type="glass", blur_radius=60,
                                      darken=0.75, theme_night_follow=False)
g1 = arr(wallpaper._blur_bg(cover_img, W, H, cg))
g2 = arr(wallpaper._blur_bg(cover_img, W, H, cg))
check("glass deterministic", float(np.abs(g1 - g2).max()) == 0.0)
# 景深：中心比角落更"有细节"（高频能量更高）
cd = dict(config.DEFAULTS); cd.update(bg_style="blur", blur_type="dof", blur_radius=60,
                                      darken=0.75, theme_night_follow=False)
dof = arr(wallpaper._blur_bg(cover_img, W, H, cd))
cen = dof[H // 2 - 100:H // 2 + 100, W // 2 - 100:W // 2 + 100]
cor = dof[0:200, 0:200]
hf_c = float(np.abs(np.diff(cen, axis=0)).mean())
hf_e = float(np.abs(np.diff(cor, axis=0)).mean())
check("dof center sharper", hf_c > hf_e * 1.2, f"center={hf_c:.2f} corner={hf_e:.2f}")
# 缓存键区分类型
wallpaper._BG_CACHE.clear()
c1 = dict(config.DEFAULTS); c1.update(bg_style="blur", blur_type="gauss", blur_radius=60,
                                      darken=0.75, theme_night_follow=False)
c2 = {**c1, "blur_type": "box"}
wallpaper._get_bg(cover, W, H, c1)
wallpaper._get_bg(cover, W, H, c2)
check("bg cache keyed by type", len(wallpaper._BG_CACHE) == 2, f"cached={len(wallpaper._BG_CACHE)}")

print()
print("RESULT:", "ALL_PASS" if not FAILS else f"FAILED={FAILS}")
sys.exit(1 if FAILS else 0)
