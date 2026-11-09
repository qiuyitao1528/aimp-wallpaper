# -*- coding: utf-8 -*-
"""把"过渡"与"像素采样红线"两条结论写进项目记忆。"""
import io
import os

P = os.path.join(os.path.expanduser("~"), ".zcode", "memory", "aimp-wallpaper-project.md")
s = io.open(P, encoding="utf-8").read()
anchor = "**⭐ 字体回退（v0.1.7，2026-11-09）**"
add = (
    "**⭐ 壁纸切换过渡（2026-11-09 结论）**：Windows 自身是否对程序化 SetWallpaper 做渐变"
    "**会随 shell/DWM 状态变化**——同一台机器曾连续数小时硬切（6 种调用组合 + 系统动画全开仍无过渡），"
    "后又自行恢复渐变（红→蓝 316ms~1s、11 帧中间色），期间 explorer 未重启。"
    "**结论：不自己造过渡，交给系统**；已实现的覆盖层方案会遮挡系统效果且有闪烁风险，v0.1.9 全部移除。\n"
    "**⭐ 像素采样测试红线**：采样点必须先校验\"确实是桌面\"（先铺已知纯色壁纸，扫描出精确匹配点），"
    "否则被前台窗口挡住会读到窗口色，导致\"无过渡/无变化\"的错误结论（本日误判两次）。\n"
)
if "壁纸切换过渡（2026-11-09 结论）" not in s:
    s = s.replace(anchor, add + anchor, 1)
    io.open(P, "w", encoding="utf-8").write(s)
    print("记忆已更新")
else:
    print("已存在，跳过")
