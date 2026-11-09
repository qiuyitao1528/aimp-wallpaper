# -*- coding: utf-8 -*-
"""修：过渡结束闪回上一张（撤覆盖层早于 shell 真正换图）。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()

if "_FADE_GRACE_S" in s:
    print("已修过")
    raise SystemExit

# 1) 常量
s = s.replace("class _IDesktopWallpaper2", "_FADE_GRACE_S = 0.4  # 换图后保持覆盖层的时间（等 shell 刷屏）\n\n\nclass _IDesktopWallpaper2", 1)
if "_FADE_GRACE_S" not in s:
    # 退而求其次：插在 DWPOS_ 常量行后
    s = s.replace("DWPOS_CENTER, DWPOS_TILE, DWPOS_STRETCH, DWPOS_FIT, DWPOS_FILL, DWPOS_SPAN = 0, 1, 2, 3, 4, 5",
                  "DWPOS_CENTER, DWPOS_TILE, DWPOS_STRETCH, DWPOS_FIT, DWPOS_FILL, DWPOS_SPAN = 0, 1, 2, 3, 4, 5\n"
                  "_FADE_GRACE_S = 0.4  # 换图后保持覆盖层的时间（等 shell 真正刷到桌面）")

# 2) 换图后等待再撤层
OLD = """        dw.SetPosition(DWPOS_FILL)
    finally:
        if overlays:"""
NEW = """        dw.SetPosition(DWPOS_FILL)
        if overlays:
            # shell 处理 SetWallpaper 有延迟（实测约 300ms），过早撤层会闪回旧图
            time.sleep(_FADE_GRACE_S)
    finally:
        if overlays:"""
if OLD not in s:
    print("未匹配到换图块")
    raise SystemExit
s = s.replace(OLD, NEW)

# 3) 确保 import time
if "\nimport time\n" not in s:
    s = s.replace("import sys\n", "import sys\nimport time\n", 1)

io.open(P, "w", encoding="utf-8").write(s)
print("已修：换图后等 %.1fs 再撤覆盖层" % 0.4)
