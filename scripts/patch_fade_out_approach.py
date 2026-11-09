# -*- coding: utf-8 -*-
"""把过渡改成成熟做法：覆盖显示"旧图快照" → 后台换壁纸 → 等刷上 → 旧图淡出。

这样切换过程中的等待被旧图盖住（画面不变），淡出时才露出已经换好的新图，
结构性消除"过渡末尾闪回上一张"。
"""
import io

# ---------------- 1. fade.py：加 show_snapshot / fade_out ----------------
P = r"E:\aimp-wallpaper\aimp_wallpaper\fade.py"
s = io.open(P, encoding="utf-8").read()
if "def show_snapshot" not in s:
    s = s.replace("def crossfade(new_images",
'''def show_snapshot(layers, alpha: int = 255):
    """把"当前桌面样子"的旧图铺满全屏（alpha=255 时与桌面完全一致，画面上看不出变化）。"""
    overlays = []
    try:
        for x, y, w, h, img in layers:
            ov = _Overlay(x, y, w, h, img)
            ov.set_alpha(alpha)
            overlays.append(ov)
        desktop.seat_overlays()
        _pump(30)
        return overlays
    except Exception:
        destroy_all(overlays)
        raise


def fade_out(overlays, duration_ms: int = 220, fps: int = 60) -> None:
    """覆盖层常亮 alpha 从 255 降到 0，露出下面已经换好的新壁纸。"""
    if not overlays:
        return
    steps = max(2, int(duration_ms / 1000.0 * fps))
    for i in range(1, steps + 1):
        a = int(255 * (1 - i / steps))
        for ov in overlays:
            ov.set_alpha(a)
        _pump(1000.0 / fps)


def crossfade(new_images''')
    io.open(P, "w", encoding="utf-8").write(s)
    print("fade.py: 已加 show_snapshot / fade_out")
else:
    print("fade.py: 已存在")

# ---------------- 2. wallpaper.py：改渲染流程 ----------------
P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()

OLD = '''    layers = []          # 淡入用：[(x, y, w, h, img)]
    for i, m in enumerate(targets):'''
NEW = '''    old_layers = []      # 过渡用：切换前的桌面快照 [(x, y, w, h, img)]
    for m in targets:
        try:
            cur = dw.GetWallpaper(m["id"])
            if cur and os.path.exists(cur):
                with Image.open(cur) as im:
                    im.load()
                    shot = im.convert("RGB")
                if shot.size != (m["w"], m["h"]):
                    shot = shot.resize((m["w"], m["h"]), Image.BILINEAR)
                old_layers.append((m.get("left", 0), m.get("top", 0), m["w"], m["h"], shot))
        except Exception:
            old_layers = []
            break

    for i, m in enumerate(targets):'''
if OLD not in s:
    print("wallpaper: 未匹配到循环起点")
    raise SystemExit
s = s.replace(OLD, NEW)

OLD2 = '''    # 切歌淡入过渡（Windows 自身已不给渐变，这里由覆盖层画；失败则直接硬切）
    overlays = []
    if cfg.get("fade_enabled", True):
        try:
            from . import fade as _fade
            overlays = _fade.crossfade(layers, int(cfg.get("fade_ms", 220)))
        except Exception:
            overlays = []  # 过渡失败就硬切，绝不影响换壁纸
            try:
                from . import applog
                applog.log_exc("淡入过渡失败（回退为直接切换）:\\n", *sys.exc_info())
            except Exception:
                pass

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
NEW2 = '''    # 过渡（Windows 11 已不再给壁纸切换做渐变，这里自己画）：
    #   1) 用旧图铺满全屏（与当前桌面完全一致，看不出变化）
    #   2) 后台真正换壁纸（被旧图盖住）
    #   3) 等 shell 刷上新图后，旧图淡出 → 露出新壁纸
    overlays = []
    fade_ms = int(cfg.get("fade_ms", 220) or 220)
    if cfg.get("fade_enabled", True) and old_layers:
        try:
            from . import fade as _fade
            overlays = _fade.show_snapshot(old_layers)
        except Exception:
            overlays = []
            try:
                from . import applog
                applog.log_exc("过渡覆盖层创建失败（改为直接切换）:\\n", *sys.exc_info())
            except Exception:
                pass

    try:
        for m, path in zip(targets, paths):
            dw.SetWallpaper(m["id"], path)
        dw.SetPosition(DWPOS_FILL)
        if overlays:
            time.sleep(_FADE_GRACE_S)   # 等待被旧图盖住，画面无变化
            from . import fade as _fade
            _fade.fade_out(overlays, fade_ms)
    finally:
        if overlays:
            try:
                from . import fade as _fade
                _fade.destroy_all(overlays)
            except Exception:
                pass'''
if OLD2 not in s:
    print("wallpaper: 未匹配到过渡块（可能格式已变）")
    raise SystemExit
s = s.replace(OLD2, NEW2)
io.open(P, "w", encoding="utf-8").write(s)
print("wallpaper.py: 过渡已改为'旧图淡出'")
