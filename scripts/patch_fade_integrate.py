# -*- coding: utf-8 -*-
"""把淡入过渡接进 render_and_apply：先全部存盘 → 淡入 → SetWallpaper → 销毁覆盖层。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()

OLD = '''    for i, m in enumerate(targets):
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
    dw.SetPosition(DWPOS_FILL)'''

NEW = '''    layers = []          # 淡入用：[(x, y, w, h, img)]
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

    # 切歌淡入过渡（Windows 自身已不给渐变，这里由覆盖层画；失败则直接硬切）
    overlays = []
    if cfg.get("fade_enabled", True):
        try:
            from . import fade as _fade
            overlays = _fade.crossfade(layers, int(cfg.get("fade_ms", 220)))
        except Exception:
            overlays = []

    try:
        for m, path in zip(targets, paths):
            dw.SetWallpaper(m["id"], path)
        dw.SetPosition(DWPOS_FILL)
    finally:
        if overlays:
            try:
                from . import fade as _fade
                _fade.destroy_all(overlays)
            except Exception:
                pass'''

if OLD in s:
    s = s.replace(OLD, NEW)
    io.open(P, "w", encoding="utf-8").write(s)
    print("render_and_apply 已接入淡入")
else:
    print("未匹配到 render_and_apply 主体")
