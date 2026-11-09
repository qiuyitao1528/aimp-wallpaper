# -*- coding: utf-8 -*-
"""记录切歌提速结论与线程异常教训。"""
import io
import os

P = os.path.join(os.path.expanduser("~"), ".zcode", "memory", "aimp-wallpaper-project.md")
s = io.open(P, encoding="utf-8").read()
anchor = "**⭐ 壁纸切换过渡（2026-11-09 结论）**"
add = (
    "**⭐ 切歌提速（v0.2.0）**：延迟构成 = 检测（轮询+去抖）+ 封面等待（AIMP 自身约 250~300ms，压不下去）"
    "+ 渲染换图（~190ms）+ Windows 刷屏（30~380ms，外部）。已做：轮询 120ms/去抖 0.2s、封面 50ms 首试 + 60ms 密集重试、"
    "同专辑连播快速路径（先用上张封面）、渲染 87→58ms（背景 1/4 降采样 + BOX 缩小、封面投影 1/3 尺寸、亮度饱和度在小图算）、"
    "显示器列表 10s 缓存。实测单次 547→440~500ms。每次切换写日志 `[切歌] 耗时: 封面 Xms + 渲染换图 Yms`。\n"
    "**⭐ 线程静默崩溃教训**：--windowed 下 worker 线程抛异常（本次是 `__main__.py` 漏 `import time`）等于完全静默、壁纸直接不更新。"
    "已加 `threading.excepthook` 统一落盘；**任何新增在 worker 里用的模块/变量都要先在日志里确认线程活着**。\n"
)
if "切歌提速（v0.2.0）" not in s:
    s = s.replace(anchor, add + anchor, 1)
    io.open(P, "w", encoding="utf-8").write(s)
    print("记忆已更新")
else:
    print("已存在")
