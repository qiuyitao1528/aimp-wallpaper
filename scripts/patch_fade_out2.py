# -*- coding: utf-8 -*-
"""改为"旧图快照淡出"方案（结构性消除末尾闪回）。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()

# 1) 循环前先抓旧图快照
OLD_HEAD = """    layers = []          # 淡入用：[(x, y, w, h, img)]
    for i, m in enumerate(targets):"""
NEW_HEAD = """    # 切换前的桌面快照（用于"旧图淡出"过渡）
    old_layers = []
    for m in targets:
        try:
            cur = dw.GetWallpaper(m["id"])
            if not cur or not os.path.exists(cur):
                old_layers = []
                break
            with Image.open(cur) as im:
                im.load()
                shot = im.convert("RGB")
            if shot.size != (m["w"], m["h"]):
                shot = shot.resize((m["w"], m["h"]), Image.BILINEAR)
            old_layers.append((m.get("left", 0), m.get("top", 0), m["w"], m["h"], shot))
        except Exception:
            old_layers = []
            break

    layers = []          # 新图（供失败回退用）
    for i, m in enumerate(targets):"""
if OLD_HEAD in s:
    s = s.replace(OLD_HEAD, NEW_HEAD)
else:
    print("头段未匹配")

# 2) 过渡块整体替换
start = s.find("    # 切歌淡入过渡（Windows 自身已不给渐变，这里由覆盖层画；失败则直接硬切）")
end = s.find("    # 可视化面板锚点：屏幕坐标", start)
if start < 0 or end < 0:
    print("过渡块定位失败")
    raise SystemExit

NEW_BLOCK = '''    # 过渡（Win11 已不再给壁纸切换做渐变，这里自己画）：
    #   1) 旧图铺满全屏——与当前桌面完全一致，画面上看不出任何变化
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
            time.sleep(_FADE_GRACE_S)   # 等新图刷上（被旧图盖住，看不到等待）
            from . import fade as _fade
            _fade.fade_out(overlays, fade_ms)
    finally:
        if overlays:
            try:
                from . import fade as _fade
                _fade.destroy_all(overlays)
            except Exception:
                pass
'''
s = s[:start] + NEW_BLOCK + s[end:]
io.open(P, "w", encoding="utf-8").write(s)
print("已改为旧图淡出方案")
