# -*- coding: utf-8 -*-
"""只读探针：读 AIMP 共享内存拿当前曲目，用真实配置离线复现折行，输出每行宽度。

不读图进上下文、不写任何用户数据；结果写 ASCII 文件后由调用方 cat。
运行：uv run python -I scripts/probe_wrap.py
"""
import ctypes
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aimp_wallpaper import config, wallpaper  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

OUT = []


def emit(s):
    OUT.append(s)


# ---- 1. AIMP 共享内存（2048B）：0x28 起 6 个 WCHAR 长度，0x58 起紧凑 UTF-16 ----
try:
    k32 = ctypes.WinDLL("kernel32")
    k32.OpenFileMappingW.restype = ctypes.c_void_p
    k32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    k32.MapViewOfFile.restype = ctypes.c_void_p
    k32.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_uint32, ctypes.c_size_t]
    k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    FILE_MAP_READ = 0x0004
    h = k32.OpenFileMappingW(FILE_MAP_READ, False, "AIMP2_RemoteInfo")
    if not h:
        emit("AIMP_MAP: not found (AIMP not running?)")
        title, artist, album = "", "", ""
    else:
        view = k32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, 2048)
        if not view:
            raise OSError("MapViewOfFile failed")
        try:
            raw = ctypes.string_at(view, 2048)
            lens = [int.from_bytes(raw[0x28 + i * 4:0x2C + i * 4], "little") for i in range(6)]
            # 顺序：Album/Artist/Date/FileName/Genre/Title
            names = ["album", "artist", "date", "filename", "genre", "title"]
            pos = 0x58
            vals = {}
            for name, ln in zip(names, lens):
                vals[name] = raw[pos:pos + ln * 2].decode("utf-16-le", errors="replace")
                pos += ln * 2
            title, artist, album = vals["title"], vals["artist"], vals["album"]
            emit("TRACK title=" + ascii(title))
            emit("TRACK artist=" + ascii(artist))
            emit("TRACK album=" + ascii(album))
        finally:
            k32.UnmapViewOfFile(view)
except Exception as e:
    emit("AIMP_MAP error: " + repr(e)[:200])
    title, artist, album = "", "", ""

# ---- 2. 真实配置（只读 %LOCALAPPDATA% 的安装版配置）----
live_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "aimp-wallpaper", "config.json")
data = json.load(open(live_path, encoding="utf-8"))
cfg = {**config.DEFAULTS, **data}
emit("CFG title_overflow=" + str(cfg.get("title_overflow")) +
     " space_window=" + str(cfg.get("title_space_window")) +
     " bracket=" + str(cfg.get("title_bracket_break")) +
     " align=" + str(cfg.get("text_align")) +
     " offset_x=" + str(cfg.get("text_offset_x")) +
     " size_ratio=" + str(cfg.get("title_size_ratio")))

# ---- 3. 按渲染几何复现折行 ----
W, H = 1920, 1080
font = wallpaper._load_font(bool(cfg.get("title_bold", True)),
                            int(H * float(cfg.get("title_size_ratio", 0.075))),
                            cfg.get("title_font_file"))[0]
draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))
cw = int(H * 0.82)  # 封面等比高度（封面足够大时的近似，与实际渲染一致的量级）
cx = int(H * cfg["cover_margin_ratio"]) + int(cfg.get("cover_offset_x", 0) or 0)
tx = cx + cw + int(H * 0.055) + int(cfg.get("text_offset_x", 0) or 0)
tw_max = W - tx - int(W * 0.06)
emit(f"GEOM tx={tx} tw_max={tw_max} screen_right_margin={int(W*0.06)}")

lines = wallpaper._wrap_title(
    draw, title, font, tw_max, 4,
    max(0, min(20, int(cfg.get("title_space_window", 0) or 0))),
    bool(cfg.get("title_bracket_break", True)))
for i, ln in enumerate(lines):
    wpx = wallpaper._text_len(draw, ln, font)
    emit(f"LINE{i} width={wpx:.0f} over_tw={wpx - tw_max:+.0f} over_screen={tx + wpx - W:+.0f} " + ascii(ln))

open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_probe_out.txt"),
     "w", encoding="utf-8").write("\n".join(OUT))
print("PROBE_DONE")
