# -*- coding: utf-8 -*-
import io

p = r"E:\aimp-wallpaper\README.md"
s = io.open(p, encoding="utf-8").read()
s = s.replace("附带 AIMP 经典样式频谱面板、桌面音乐控件与系统托盘。",
              "附带 AIMP 经典样式频谱面板与系统托盘。")
s = s.replace("- **桌面音乐控件**：封面缩略图、播放/暂停/上下曲、进度条拖动\n", "")
s = s.replace("- 频谱面板与小部件右键：拖动定位", "- 频谱面板右键：拖动定位")
io.open(p, "w", encoding="utf-8").write(s)
print("剩余含'控件'行数:", sum(1 for ln in s.splitlines() if "控件" in ln))
