# -*- coding: utf-8 -*-
"""渲染基准：量切歌/暂停切换的渲染+落盘耗时（假 COM，不碰桌面壁纸）。"""
import io
import sys
import tempfile
import time

sys.path.insert(0, ".")
from PIL import Image  # noqa: E402

from aimp_wallpaper import config, wallpaper  # noqa: E402

TMP = tempfile.mkdtemp(prefix="aimpwp_bench_")


class FakeDW:
    def SetWallpaper(self, mid, path):
        return None

    def GetPosition(self):
        return 4


wallpaper._get_wallpaper_com = lambda: FakeDW()
cfg = dict(config.DEFAULTS)
cfg.update({"output_dir": TMP, "fade_native": False})
monitors = [{"id": "MONO", "w": 1920, "h": 1080, "left": 0, "top": 0}]


def make_cover(seed):
    img = Image.new("RGB", (3000, 3000))
    for y in range(0, 3000, 7 + seed):
        for x in range(0, 3000, 11 + seed):
            img.putpixel((x, y), (x % 255, y % 255, (x + y) % 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


cover_a = make_cover(0)
cover_b = make_cover(1)  # 另一张真封面
meta_a = {"title": "基准歌名 Alpha", "artist": "歌手一", "album": "专辑A", "filename": "a.flac",
          "duration_ms": 200000, "samplerate": 48000, "file_size": 30000000, "bit_rate": 1000}
meta_b = {"title": "基准歌名 Beta Second Line Much Longer Text For Wrapping", "artist": "歌手二",
          "album": "专辑B", "filename": "b.flac", "duration_ms": 210000,
          "samplerate": 44100, "file_size": 31000000, "bit_rate": 1100}


def bench(label, cover, meta, n=3):
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        wallpaper.render_and_apply(cover, meta, cfg, monitors)
        ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    print(f"{label:28s} 中位 {ts[len(ts) // 2]:6.1f} ms   最快 {ts[0]:6.1f} ms")


print("== 切歌渲染基准（1920x1080，含 PNG 落盘）==")
bench("换专辑（解码+模糊+渲染）", cover_a, meta_a)
bench("同专辑连播（缓存全命中）", cover_a, meta_b)
bench("换专辑反方向（缓存1张重建）", cover_b, meta_b)
cfg["pause_mode"] = "darken"
bench("暂停切换（bg 级压暗复用）", cover_a, meta_a)
cfg["pause_mode"] = "both"
bench("暂停切换（整幅压暗+角标）", cover_a, meta_a)
print(f"\n临时目录: {TMP}")
