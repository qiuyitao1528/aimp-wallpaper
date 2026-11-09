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
               "sub_color": "#FF0000", "sub_overflow": "wrap", "sub_size_ratio": 0.03,
               "wrap_space_window": 3, "blur_type": "motion"}, f)
config.CONFIG_PATH, _saved_path = old_cfg_path, config.CONFIG_PATH
cfg = config.load()
check("migrate artist_size", cfg["artist_size_ratio"] == 0.03)
check("migrate album_font", cfg["album_font_file"] == "simhei.ttf")
check("migrate artist_bold", cfg["artist_bold"] is True and cfg["album_bold"] is True)
check("migrate colors", cfg["artist_color"] == "#FF0000" and cfg["album_color"] == "#FF0000")
check("migrate overflow", cfg["artist_overflow"] == "wrap" and cfg["album_overflow"] == "wrap")
check("migrate shadows off", cfg["title_shadow"] is False and cfg["artist_shadow"] is False
      and cfg["album_shadow"] is False)
check("migrate wrap windows", cfg["title_space_window"] == 3 and cfg["artist_space_window"] == 3
      and cfg["album_space_window"] == 3)
check("migrate blur type to gauss", cfg["blur_type"] == "gauss")

new_cfg_path = os.path.join(tmp, "new", "config.json")
os.makedirs(os.path.dirname(new_cfg_path), exist_ok=True)
with open(new_cfg_path, "w", encoding="utf-8") as f:
    json.dump({"artist_size_ratio": 0.09, "text_shadow": False, "wrap_space_window": 7}, f)
config.CONFIG_PATH = new_cfg_path
cfg = config.load()
check("new cfg untouched", cfg["artist_size_ratio"] == 0.09)
check("v024 cfg wrap seeded", cfg["title_space_window"] == 7 and cfg["album_space_window"] == 7)
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
# 括号断行：关=普通断行（行尾孤括号）/ 开=闭合括号贴近则吸收 / 组离行首远则整组下移
text_b = "aaaa (bb) cc"
wb1 = wallpaper._text_len(draw, "aaaa (bb", font)
wb2 = wallpaper._text_len(draw, "aaaa (bb)", font)
max_b = (wb1 + wb2) / 2  # 让自然断点恰好落在 ")" 之前
lb0 = wallpaper._wrap_title(draw, text_b, font, max_b, 2, space_window=0)
lb1 = wallpaper._wrap_title(draw, text_b, font, max_b, 2, space_window=0, bracket_break=True)
lb2 = wallpaper._wrap_title(draw, text_b, font, max_b, 2, space_window=2, bracket_break=True)
print("bracket off:", ascii(lb0), "| move:", ascii(lb1), "| absorb:", ascii(lb2))
check("bracket off normal", lb0[1].startswith(")"), ascii(lb0))
check("bracket move group", lb1[0] == "aaaa" and lb1[1].startswith("(bb"), ascii(lb1))
check("bracket absorb close", lb2[0] == "aaaa (bb)" and lb2[1] == "cc", ascii(lb2))
text_g = "aa (bbbbbbbb) cc"
wg1 = wallpaper._text_len(draw, "aa (b", font)
wg2 = wallpaper._text_len(draw, "aa (bb", font)
lg = wallpaper._wrap_title(draw, text_g, font, (wg1 + wg2) / 2, 2, space_window=2, bracket_break=True)
print("bracket group move:", ascii(lg))
check("bracket group to next line", lg[0] == "aa" and lg[1].startswith("("), ascii(lg))
# 吸收宽度上限（2026-11-10 真实事故回归：括号吸收把行顶出屏幕被裁）
text_r = "aaaa (bbbb) cc"
wr1 = wallpaper._text_len(draw, "aaaa (bb", font)
wr2 = wallpaper._text_len(draw, "aaaa (bbb", font)
wr_full = wallpaper._text_len(draw, "aaaa (bbbb)", font)
lr = wallpaper._wrap_title(draw, text_r, font, (wr1 + wr2) / 2, 2, space_window=5,
                           bracket_break=True, line_limit=wr_full - 10)
print("bracket guard:", ascii(lr))
check("bracket absorb guarded", lr[0] == "aaaa" and lr[1].startswith("(bbbb"), ascii(lr))
lr0 = wallpaper._wrap_title(draw, text_r, font, (wr1 + wr2) / 2, 2, space_window=5,
                            bracket_break=True)
check("bracket absorb unguarded ok", lr0[0].startswith("aaaa (bbbb"), ascii(lr0))
ws1 = wallpaper._text_len(draw, "aaaa bbbb", font)
ws2 = wallpaper._text_len(draw, "aaaa bbbbb", font)
ls = wallpaper._wrap_title(draw, "aaaa bbbbb ccc", font, (ws1 + ws2) / 2, 2,
                           space_window=10,
                           line_limit=wallpaper._text_len(draw, "aaaa bbbbb ", font) - 10)
print("space guard:", ascii(ls))
check("space absorb guarded", ls[0] == "aaaa bbbb", ascii(ls))
# 真实事故：Cry For Me (feat. Ami) (为我哭泣) —— 括号吸收整组超屏幕预算 → 整组下移
title_r = "Cry For Me (feat. Ami) (为我哭泣)"
wr_a = wallpaper._text_len(draw, "Cry For Me (feat. Ami) (为我", font)
wr_b = wallpaper._text_len(draw, "Cry For Me (feat. Ami) (为我哭", font)
lr2 = wallpaper._wrap_title(draw, title_r, font, (wr_a + wr_b) / 2, 2, space_window=5,
                            bracket_break=True, line_limit=wr_a + 40)
print("real case:", ascii(lr2))
check("real case guarded", len(lr2) == 2 and all(
    wallpaper._text_len(draw, ln, font) <= wr_a + 40 for ln in lr2), ascii(lr2))
# 换行模式无省略号：3 行文本 → 3 行全展示，任何一行都不含 …
text3 = "aaaa bb cc dd ee ff gg"
w3a = wallpaper._text_len(draw, "aaaa bb", font)
w3b = wallpaper._text_len(draw, "aaaa bb cc", font)
l3 = wallpaper._wrap_title(draw, text3, font, (w3a + w3b) / 2, 4)
print("3-line wrap:", ascii(l3))
check("wrap 3 lines no ellipsis", len(l3) == 3 and not any("…" in ln for ln in l3), ascii(l3))
# 超过行数上限 → 恰好 max_lines 行、无 … 标记
lc = wallpaper._wrap_title(draw, "aaaa bb cc dd ee ff gg hh ii jj kk ll mm nn oo", font,
                           (w3a + w3b) / 2, 2)
check("wrap cap no ellipsis", len(lc) == 2 and not any("…" in ln for ln in lc), ascii(lc))

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
win._line_vars["title"]["space_w"].set("8")
win._line_vars["artist"]["space_w"].set("关")
win._line_vars["title"]["bracket"].set(False)
win._line_vars["artist"]["bracket"].set(False)
win.bg_style_var.set("模糊+暗角")
win.night_var.set(True)
win.night_alpha_var.set("70")
win.cover_radius_var.set("24")
win.cover_sa_var.set("70")
win.cover_sw_var.set("2")
win.pause_mode_var.set("角标")
win.pause_dark_var.set("50")
win.lyr_show_var.set(True)
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
check("gui save wrap per line", saved.get("title_space_window") == 8
      and saved.get("artist_space_window") == 0 and saved.get("album_space_window") == 5,
      f"{saved.get('title_space_window')}/{saved.get('artist_space_window')}/{saved.get('album_space_window')}")
check("gui save bracket per line", saved.get("title_bracket_break") is False
      and saved.get("artist_bracket_break") is False and saved.get("album_bracket_break") is True,
      f"{saved.get('title_bracket_break')}/{saved.get('artist_bracket_break')}/{saved.get('album_bracket_break')}")
check("gui save ratio", abs(saved.get("artist_size_ratio", 0) - gui_cfg["artist_size_ratio"]) < 1e-6)
check("gui save cover style", saved.get("cover_radius") == 24 and saved.get("cover_shadow_alpha") == 70
      and saved.get("cover_stroke_w") == 2,
      f"{saved.get('cover_radius')}/{saved.get('cover_shadow_alpha')}/{saved.get('cover_stroke_w')}")
check("gui save pause", saved.get("pause_mode") == "badge" and saved.get("pause_darken") == 50,
      f"{ascii(saved.get('pause_mode'))}/{saved.get('pause_darken')}")
check("gui save lyrics show", saved.get("lyrics_hidden") is False)

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

# ---------- G. 模糊类型：高斯系四变体 gauss/soft/fog/glow ----------
BLUR_TYPES = ("gauss", "soft", "fog", "glow")
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
for t in ("soft", "fog", "glow"):
    d = float(np.abs(blurs[t] - blurs["gauss"]).mean())
    check(f"blur_type {t} differs from gauss", d > 0.2, f"meandiff={d:.2f}")
def struct_res(a):  # 结构残差：输出 vs 自身 1/16 降采样回放大（越无结构越小）
    small = np.asarray(Image.fromarray(a.astype(np.uint8))
                       .resize((W // 16, H // 16), Image.BOX).resize((W, H), Image.BILINEAR),
                       dtype=np.float64)
    return float(np.abs(a - small).mean())
check("glow brighter than gauss", blurs["glow"].mean() > blurs["gauss"].mean(),
      f"glow={blurs['glow'].mean():.1f} gauss={blurs['gauss'].mean():.1f}")
check("soft close to gauss", float(np.abs(blurs["soft"] - blurs["gauss"]).mean()) < 15.0,
      f"meandiff={float(np.abs(blurs['soft'] - blurs['gauss']).mean()):.2f}")
# 雾面强度越大越无结构（r=100 的结构残差 < r=40）
cf = dict(config.DEFAULTS); cf.update(bg_style="blur", blur_type="fog", darken=0.75,
                                      theme_night_follow=False)
r100 = arr(wallpaper._blur_bg(cover_img, W, H, {**cf, "blur_radius": 100}))
r40 = arr(wallpaper._blur_bg(cover_img, W, H, {**cf, "blur_radius": 40}))
check("fog stronger=flatter", struct_res(r100) < struct_res(r40),
      f"r100={struct_res(r100):.3f} r40={struct_res(r40):.3f}")
# 缓存键区分类型
wallpaper._BG_CACHE.clear()
c1 = dict(config.DEFAULTS); c1.update(bg_style="blur", blur_type="gauss", blur_radius=60,
                                      darken=0.75, theme_night_follow=False)
c2 = {**c1, "blur_type": "soft"}
wallpaper._get_bg(cover, W, H, c1)
wallpaper._get_bg(cover, W, H, c2)
check("bg cache keyed by type", len(wallpaper._BG_CACHE) == 2, f"cached={len(wallpaper._BG_CACHE)}")

print()

# ---------- H. 歌词 + 封面样式 + 暂停显示 ----------
from aimp_wallpaper.lyrics import LyricsWindow, fetch_lrc, parse_lrc  # noqa: E402

lrc = "[ti:x]\n[00:01.50]第一句\n[00:03]第二句<00:03.20>词级\n[offset:500]\n[00:05.00]第三句\n"
parsed = parse_lrc(lrc)
check("lrc count", len(parsed) == 3, str(parsed))
check("lrc offset", parsed[2][0] == 5500, str(parsed[2]))
check("lrc wordtag stripped", parsed[1][1] == "第二句词级", ascii(parsed[1][1]))

# 本地 .lrc 链路（不联网）
lrc_dir = tempfile.mkdtemp(prefix="aw_lrc_")
song_dir = os.path.join(lrc_dir, "music")
os.makedirs(song_dir)
with open(os.path.join(song_dir, "testsong.lrc"), "w", encoding="utf-8") as f:
    f.write("[00:01.00]hello\n")
got = fetch_lrc("testsong", "someone", None, os.path.join(lrc_dir, "cache"),
                os.path.join(song_dir, "testsong.mp3"))
check("lrc local fetch", bool(got) and got[0][1] == "hello", str(got))

# 歌词样式播种：旧配置无 lyrics_* 键 → 从 title_* 播种
seed_path = os.path.join(tmp, "seed", "config.json")
os.makedirs(os.path.dirname(seed_path), exist_ok=True)
with open(seed_path, "w", encoding="utf-8") as f:
    json.dump({"title_font_file": "simhei.ttf", "title_color": "#FFE000", "title_shadow": False}, f)
config.CONFIG_PATH = seed_path
cfg2 = config.load()
check("lyrics style seeded", cfg2["lyrics_font_file"] == "simhei.ttf"
      and cfg2["lyrics_color"] == "#FFE000" and cfg2["lyrics_shadow"] is False,
      f"{cfg2['lyrics_font_file']}/{cfg2['lyrics_color']}/{cfg2['lyrics_shadow']}")
config.CONFIG_PATH = _saved_path

# 封面样式键：圆角/描边/去阴影各自产生可见差异
cfg_c = dict(config.DEFAULTS)
cfg_c.update(bg_style="blur", blur_radius=60, darken=0.75, show_text=True, theme_night_follow=False)
base_c = arr(wallpaper.render_poster(cover, meta, W, H, cfg_c))
check("cover radius works", np.abs(arr(wallpaper.render_poster(
    cover, meta, W, H, {**cfg_c, "cover_radius": 48})) - base_c).sum() > 1000)
check("cover stroke works", np.abs(arr(wallpaper.render_poster(
    cover, meta, W, H, {**cfg_c, "cover_stroke_w": 4, "cover_stroke_color": "#FF0000"})) - base_c).sum() > 1000)
check("no shadow works", np.abs(arr(wallpaper.render_poster(
    cover, meta, W, H, {**cfg_c, "cover_shadow_alpha": 0})) - base_c).sum() > 1000)

# 暂停：压暗更暗 / 角标右下角出现 / 不暂停与基线一致
paused_d = wallpaper.render_poster(cover, meta, W, H,
                                   {**cfg_c, "pause_mode": "darken", "pause_darken": 40}, paused=True)
check("pause darken", arr(paused_d).mean() < base_c.mean(),
      f"{arr(paused_d).mean():.1f} vs {base_c.mean():.1f}")
paused_b = wallpaper.render_poster(cover, meta, W, H, {**cfg_c, "pause_mode": "badge"}, paused=True)
corner_b = arr(paused_b)[int(H * 0.9):, int(W * 0.85):]
corner_0 = base_c[int(H * 0.9):, int(W * 0.85):]
check("pause badge corner", np.abs(corner_b - corner_0).sum() > 5000,
      f"diff={np.abs(corner_b - corner_0).sum():.0f}")
check("no pause matches base", abs(arr(wallpaper.render_poster(
    cover, meta, W, H, cfg_c, paused=False)).mean() - base_c.mean()) < 0.001)


# LyricsWindow 离屏 smoke（创建→渲染→销毁，窗口立即隐藏）
class FakeIpc:
    def snapshot(self):
        return {"position_ms": 0, "duration_ms": 200000, "connected": True,
                "title": "t", "filename": None}


root3 = tk.Tk()
root3.withdraw()
try:
    lw = LyricsWindow(root3, FakeIpc(), config.load(), lambda: None)
    lw.win.withdraw()
    lw.set_lines([(0, "第一句"), (1500, "第二句")])
    lw._render("第一句", "第二句")
    check("lyrics window smoke", lw.H > 20 and lw._shown_pair == ("第一句", "第二句"),
          f"H={lw.H} pair={ascii(lw._shown_pair)}")
    lw.win.destroy()
except Exception as e:  # 离屏环境可能拿不到 ULW，失败不掩盖其余结论
    check("lyrics window smoke", False, repr(e)[:120])
root3.destroy()

print()
print("RESULT:", "ALL_PASS" if not FAILS else f"FAILED={FAILS}")
sys.exit(1 if FAILS else 0)
