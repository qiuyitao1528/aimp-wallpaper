# -*- coding: utf-8 -*-
"""同专辑连播时先用上一首封面立即换壁纸（不等 AIMP 回封面），封面若真的不同再补渲染。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\__main__.py"
s = io.open(P, encoding="utf-8").read()

OLD = '''        t_wait0 = time.monotonic()
        cover = ipc.wait_cover(gen, timeout=12.0)  # 覆盖 10s 封面重试窗口
        cover_ms = (time.monotonic() - t_wait0) * 1000
        t_render0 = time.monotonic()
        if render(cover, snap, "切歌"):
            render_ms = (time.monotonic() - t_render0) * 1000
            applog.log(f"[切歌] 耗时: 封面 {cover_ms:.0f}ms + 渲染换图 {render_ms:.0f}ms "
                       f"= {cover_ms + render_ms:.0f}ms")
            last_gen = gen
            last_cover, last_meta = cover, {k: snap[k] for k in ("title", "artist", "album")}'''

NEW = '''        meta_now = {k: snap[k] for k in ("title", "artist", "album")}

        # 同专辑连播：封面几乎必与上一首相同，先用上一张立即换壁纸，不等 AIMP 回图
        same_album = (last_cover is not None and last_meta is not None and meta_now["album"]
                      and meta_now["album"] == last_meta.get("album")
                      and meta_now["artist"] == last_meta.get("artist"))
        if same_album:
            t0 = time.monotonic()
            if render(last_cover, meta_now, "同专辑"):
                ms = (time.monotonic() - t0) * 1000
                applog.log(f"[切歌] 同专辑快速路径 耗时 {ms:.0f}ms（不等封面）")
                last_gen, last_meta = gen, meta_now
                real = ipc.wait_cover(gen, timeout=6.0)  # 后台确认封面是否真的相同
                if real and real != last_cover:
                    applog.log("[切歌] 实际封面与上一首不同，补渲染")
                    render(real, meta_now, "封面更新")
                    last_cover = real
                continue

        t_wait0 = time.monotonic()
        cover = ipc.wait_cover(gen, timeout=12.0)  # 覆盖 10s 封面重试窗口
        cover_ms = (time.monotonic() - t_wait0) * 1000
        t_render0 = time.monotonic()
        if render(cover, snap, "切歌"):
            render_ms = (time.monotonic() - t_render0) * 1000
            applog.log(f"[切歌] 耗时: 封面 {cover_ms:.0f}ms + 渲染换图 {render_ms:.0f}ms "
                       f"= {cover_ms + render_ms:.0f}ms")
            last_gen = gen
            last_cover, last_meta = cover, meta_now'''

if OLD in s:
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("已加同专辑快速路径")
else:
    print("未匹配")
