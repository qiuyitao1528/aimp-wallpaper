# -*- coding: utf-8 -*-
"""设置项全量往返测试：每项改成新值 → 保存 → 重新读取 → 核对。
先备份真实 config，测完原样还原。"""
import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, r"E:\aimp-wallpaper")

import tkinter as tk

from aimp_wallpaper import config, settings_gui as sg

REAL = config.CONFIG_PATH
BACKUP = REAL + ".bak-test"
shutil.copyfile(REAL, BACKUP)
tmp = tempfile.mkdtemp()
sg.startup_lnk_path = lambda: os.path.join(tmp, "AIMP Wallpaper.lnk")

failures = []
try:
    cfg = config.load()
    root = tk.Tk()
    root.withdraw()
    root.update()
    sw = sg.SettingsWindow(root, cfg)
    root.update()

    sw.blur_var.set("40")
    sw.cover_scale_var.set("0.7")
    sw.cover_dx_var.set("60")
    sw.cover_dy_var.set("-30")
    sw.title_px_var.set("96")
    sw.sub_px_var.set("52")
    sw.tsg_var.set("28")
    sw.tlg_var.set("16")
    sw.slg_var.set("20")
    sw.text_dx_var.set("100")
    sw.text_dy_var.set("-60")
    sw.text_align_var.set("居中")
    sw.text_valign_var.set("底部")
    sw.fps_var.set("60")
    sw.title_color_var.set("#FF8000")
    sw.sub_color_var.set("#00FF80")
    sw.title_of_var.set("省略号")
    sw.sub_of_var.set("换行")
    sw.shadow_var.set(False)
    sw.tbold_var.set(False)
    sw.sbold_var.set(True)
    sw.lock_var.set(True)
    sw.restore_var.set(False)
    sw.autostart_var.set(True)
    sw._save()
    print("状态栏:", sw.status.cget("text"))

    saved = json.load(io.open(config.CONFIG_PATH, encoding="utf-8"))
    sh = sw.screen_h
    checks = [
        ("blur_radius", 40), ("cover_scale", 0.7),
        ("cover_offset_x", 60), ("cover_offset_y", -30),
        ("title_size_ratio", 96 / sh), ("sub_size_ratio", 52 / sh),
        ("title_sub_gap_ratio", 28 / sh), ("title_line_gap_ratio", 16 / sh),
        ("sub_line_gap_ratio", 20 / sh),
        ("text_offset_x", 100), ("text_offset_y", -60),
        ("text_align", "center"), ("text_valign", "bottom"),
        ("vis_fps", 60), ("title_color", "#FF8000"), ("sub_color", "#00FF80"),
        ("title_overflow", "ellipsis"), ("sub_overflow", "wrap"),
        ("text_shadow", False), ("title_bold", False), ("sub_bold", True),
        ("vis_locked", True), ("restore_on_quit", False),
    ]
    for key, want in checks:
        got = saved.get(key)
        okv = (abs(got - want) < 1e-6) if isinstance(want, float) else (got == want)
        print(("  OK   " if okv else "  FAIL ") + f"{key}: {got!r}")
        if not okv:
            failures.append(key)

    # 往返：重开窗口应回显保存值
    sw2 = sg.SettingsWindow(root, config.load())
    root.update()
    echo = {
        "封面大小": (sw2.cover_scale_var.get(), "0.7"),
        "封面X": (sw2.cover_dx_var.get(), "60"),
        "文字对齐": (sw2.text_align_var.get(), "居中"),
        "垂直对齐": (sw2.text_valign_var.get(), "底部"),
        "FPS": (sw2.fps_var.get(), "60"),
        "过长": (sw2.title_of_var.get(), "省略号"),
    }
    for name, (got, want) in echo.items():
        okv = got == want
        print(("  OK   " if okv else "  FAIL ") + f"回显 {name}: {got!r}")
        if not okv:
            failures.append(f"回显{name}")
    root.destroy()
finally:
    shutil.copyfile(BACKUP, REAL)
    os.remove(BACKUP)
    print("已还原真实 config")

print("=== 结果:", "全部通过" if not failures else f"失败 {failures}", "===")
