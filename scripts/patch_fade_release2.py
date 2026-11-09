# -*- coding: utf-8 -*-
"""render_and_apply：改用 release_painted（确认桌面已换图再撤覆盖层）。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()

OLD = """        dw.SetPosition(DWPOS_FILL)
        if overlays:
            # shell 处理 SetWallpaper 有延迟（实测约 300ms），过早撤层会闪回旧图
            time.sleep(_FADE_GRACE_S)
    finally:
        if overlays:
            try:
                from . import fade as _fade
                _fade.destroy_all(overlays)
            except Exception:
                pass"""
NEW = """        dw.SetPosition(DWPOS_FILL)
    finally:
        if overlays:
            try:
                from . import fade as _fade
                # 先确认桌面真的已换成新图再撤层，否则会闪回旧图（实测刷屏延迟 30~400ms）
                _fade.release_painted(overlays, layers)
            except Exception:
                try:
                    from . import fade as _fade
                    _fade.destroy_all(overlays)
                except Exception:
                    pass"""

if OLD in s:
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("已改为 release_painted")
else:
    print("未匹配；当前片段:")
    i = s.find("dw.SetPosition(DWPOS_FILL)")
    print(s[i:i + 400])
