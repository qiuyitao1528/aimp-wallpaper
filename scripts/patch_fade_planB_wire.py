# -*- coding: utf-8 -*-
"""wallpaper.py 接入方案B 新接口（crossfade_create / crossfade_run / wait_painted）。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()

start = s.find("    # 过渡（Win11 已不再给壁纸切换做渐变，这里自己画）：")
end = s.find("    # 可视化面板锚点：屏幕坐标", start)
if start < 0 or end < 0:
    print("定位失败")
    raise SystemExit

BLOCK = '''    # 过渡（Win11 已不再给壁纸切换做渐变，这里自己画；关掉则直接用系统默认切换）：
    #   1) 旧图快照铺满全屏（与当前画面一致，看不出变化）
    #   2) 覆盖层之下真正换壁纸
    #   3) 覆盖层内旧图→新图交叉淡化（默认 220ms）
    #   4) 确认桌面已刷上新图后再撤层（否则会闪回旧图）
    overlays = []
    fade_ms = int(cfg.get("fade_ms", 220) or 220)
    if cfg.get("fade_enabled", True) and old_layers:
        try:
            from . import fade as _fade
            overlays = _fade.crossfade_create(old_layers, layers)
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
            from . import fade as _fade
            _fade.crossfade_run(overlays, fade_ms)
            _fade.wait_painted(layers)
    finally:
        if overlays:
            try:
                from . import fade as _fade
                _fade.destroy_all(overlays)
            except Exception:
                pass
'''
s = s[:start] + BLOCK + s[end:]
io.open(P, "w", encoding="utf-8").write(s)
print("wallpaper.py 已接入方案B")
