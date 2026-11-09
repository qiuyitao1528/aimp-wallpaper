"""设置窗口：开机自启 / 退出恢复原壁纸 / 歌名副行字号与字体（分开）/ 纵向间距。"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tkinter as tk
from tkinter import colorchooser, ttk

from . import config, desktop

SIZE_CHOICES = [32, 40, 48, 56, 64, 72, 80, 96, 112, 128, 144, 160]
GAP_CHOICES = [0, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40]
FONTS_FALLBACK = [
    ("微软雅黑（默认）", "msyhbd.ttc"), ("微软雅黑 常规", "msyh.ttc"), ("微软雅黑 Light", "msyhl.ttc"),
    ("黑体", "simhei.ttf"), ("宋体", "simsun.ttc"), ("楷体", "simkai.ttf"),
    ("仿宋", "simfang.ttf"), ("等线", "Deng.ttf"), ("等线 Light", "DengL.ttf"),
    ("Segoe UI", "segoeui.ttf"),
]


def startup_lnk_path() -> str:
    return os.path.join(
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
        "AIMP Wallpaper.lnk")


def autostart_enabled() -> bool:
    return os.path.exists(startup_lnk_path())


def set_autostart(enabled: bool) -> bool:
    lnk = startup_lnk_path()
    try:
        if enabled:
            if getattr(sys, "frozen", False):
                target, args, wd = sys.executable, "", os.path.dirname(sys.executable)
            else:
                proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                pyw = os.path.join(proj, ".venv", "Scripts", "pythonw.exe")
                if not os.path.exists(pyw):
                    pyw = sys.executable.replace("python.exe", "pythonw.exe")
                target, args, wd = pyw, "-m aimp_wallpaper", proj
            ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{}');"
                  "$s.TargetPath='{}';$s.Arguments='{}';$s.WorkingDirectory='{}';$s.Save()").format(
                      lnk.replace("'", "''"), target.replace("'", "''"),
                      args.replace("'", "''"), wd.replace("'", "''"))
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, timeout=20)
            return os.path.exists(lnk)
        if os.path.exists(lnk):
            os.remove(lnk)
        return True
    except Exception:
        return False


def _luma(hex_color: str) -> int:
    """'#RRGGBB' 亮度（0~255），用于色块按钮上黑/白字的选择。"""
    try:
        s = hex_color.lstrip("#")
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        return (r * 299 + g * 587 + b * 114) // 1000
    except (ValueError, IndexError):
        return 0


def _available_fonts() -> list[tuple[str, str]]:
    from . import wallpaper
    fonts = wallpaper.font_entries()
    if fonts:
        return fonts
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    return sorted((lb, f) for lb, f in FONTS_FALLBACK if os.path.exists(os.path.join(fonts_dir, f)))


class SettingsWindow:
    def __init__(self, root: tk.Tk, cfg: dict):
        self.cfg = cfg
        self.win = tk.Toplevel(root)
        self.win.title("AIMP Wallpaper 设置")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self.win.after(1000, lambda: self.win.attributes("-topmost", False))
        self.screen_h = max(1, root.winfo_screenheight())

        pad = dict(padx=10, pady=3)
        row = 0

        self.autostart_var = tk.BooleanVar(value=autostart_enabled())
        ttk.Checkbutton(self.win, text="开机自启动", variable=self.autostart_var).grid(
            row=row, column=0, columnspan=2, sticky="w", **pad)
        row += 1

        self.restore_var = tk.BooleanVar(value=bool(cfg.get("restore_on_quit", True)))
        ttk.Checkbutton(self.win, text="退出时恢复原壁纸", variable=self.restore_var).grid(
            row=row, column=0, columnspan=2, sticky="w", **pad)
        row += 1

        self.lock_var = tk.BooleanVar(value=bool(cfg.get("vis_locked")))
        ttk.Checkbutton(self.win, text="锁定频谱面板（禁拖动，仍跟随壁纸）", variable=self.lock_var).grid(
            row=row, column=0, columnspan=2, sticky="w", **pad)
        row += 1

        # 字体：注册表全量枚举（默认项置顶）；重名标签加文件名区分
        seen: dict[str, str] = {}
        deduped = []
        for lb, f in _available_fonts():
            if lb in seen:
                lb2 = f"{lb} [{os.path.basename(f)}]"
                if lb2 in seen:
                    continue
                lb = lb2
            seen[lb] = f
            deduped.append((lb, f))
        self._fonts = deduped
        self._file_to_label = {f: lb for lb, f in self._fonts}
        self._default_label = "默认（微软雅黑）"
        font_items = [self._default_label] + [lb for lb, _ in self._fonts]

        def font_row(label_text, key):
            nonlocal row
            ttk.Label(self.win, text=label_text).grid(row=row, column=0, sticky="w", **pad)
            var = tk.StringVar(value=self._file_to_label.get(cfg.get(key), self._default_label))
            ttk.Combobox(self.win, textvariable=var, values=font_items,
                         state="readonly", width=30).grid(row=row, column=1, sticky="we", **pad)
            row += 1
            return var

        # 字号/间距：具体像素值的下拉，可直接输入自定义数字
        def px_row(label_text, key, ratio_default, choices, lo, hi):
            nonlocal row
            ttk.Label(self.win, text=label_text).grid(row=row, column=0, sticky="w", **pad)
            cur = int(self.screen_h * float(cfg.get(key, ratio_default)))
            values = [str(x) for x in choices]
            if str(cur) not in values:
                values.insert(0, str(cur))
            var = tk.StringVar(value=str(cur))
            ttk.Combobox(self.win, textvariable=var, values=values, width=8).grid(
                row=row, column=1, sticky="w", **pad)
            row += 1
            return var, lo, hi

        self.title_px_var, _, _ = px_row("歌名字号(像素)", "title_size_ratio", 0.075, SIZE_CHOICES, 16, self.screen_h // 2)
        self.title_font_var = font_row("歌名字体", "title_font_file")
        self.sub_px_var, _, _ = px_row("副行字号(像素)", "sub_size_ratio", 0.042, SIZE_CHOICES, 12, self.screen_h // 2)
        self.sub_font_var = font_row("歌手·专辑字体", "sub_font_file")
        self.tlg_var, _, _ = px_row("标题行间距", "title_line_gap_ratio", 0.012, GAP_CHOICES, 0, 200)
        self.tsg_var, _, _ = px_row("标题-副行间距", "title_sub_gap_ratio", 0.02, GAP_CHOICES, 0, 200)
        self.slg_var, _, _ = px_row("副行行间距", "sub_line_gap_ratio", 0.014, GAP_CHOICES, 0, 200)

        self.shadow_var = tk.BooleanVar(value=bool(cfg.get("text_shadow", True)))
        ttk.Checkbutton(self.win, text="文字阴影", variable=self.shadow_var).grid(
            row=row, column=0, columnspan=2, sticky="w", **pad)
        row += 1

        self.tbold_var = tk.BooleanVar(value=bool(cfg.get("title_bold", True)))
        ttk.Checkbutton(self.win, text="歌名加粗", variable=self.tbold_var).grid(
            row=row, column=0, columnspan=2, sticky="w", **pad)
        row += 1

        self.sbold_var = tk.BooleanVar(value=bool(cfg.get("sub_bold", False)))
        ttk.Checkbutton(self.win, text="副行加粗", variable=self.sbold_var).grid(
            row=row, column=0, columnspan=2, sticky="w", **pad)
        row += 1

        def color_row(label_text, key, default):
            nonlocal row
            ttk.Label(self.win, text=label_text).grid(row=row, column=0, sticky="w", **pad)
            var = tk.StringVar(value=str(cfg.get(key, default) or default).upper())

            def pick():
                rgb, hexv = colorchooser.askcolor(color=var.get(), parent=self.win, title=label_text)
                if hexv:  # 取消则不改动
                    var.set(str(hexv).upper())
                    btn.configure(bg=var.get(),
                                  fg="#000000" if _luma(var.get()) > 140 else "#FFFFFF")

            btn = tk.Button(self.win, textvariable=var, bg=var.get(), relief="groove",
                            width=10, command=pick)
            btn.grid(row=row, column=1, sticky="w", **pad)
            row += 1
            return var

        def overflow_row(label_text, key, default):
            nonlocal row
            ttk.Label(self.win, text=label_text).grid(row=row, column=0, sticky="w", **pad)
            cur = cfg.get(key, default)
            var = tk.StringVar(value="换行" if cur == "wrap" else "省略号")
            ttk.Combobox(self.win, textvariable=var, values=["换行", "省略号"],
                         state="readonly", width=8).grid(row=row, column=1, sticky="w", **pad)
            row += 1
            return var

        self.title_of_var = overflow_row("歌名过长", "title_overflow", "wrap")
        self.sub_of_var = overflow_row("副行过长", "sub_overflow", "ellipsis")
        self.title_color_var = color_row("歌名颜色", "title_color", "#FFFFFF")
        self.sub_color_var = color_row("副行颜色", "sub_color", "#FFFFFF")

        ttk.Label(self.win, text="刷新率(FPS)").grid(row=row, column=0, sticky="w", **pad)
        self.fps_var = tk.StringVar(value=str(int(cfg.get("vis_fps", 30) or 30)))
        ttk.Combobox(self.win, textvariable=self.fps_var, width=8,
                     values=["15", "20", "24", "30", "45", "60", "90", "120"]).grid(
            row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Button(self.win, text="保存", command=self._save).grid(row=row, column=0, columnspan=2, pady=8)

        self.status = ttk.Label(self.win, text="保存后壁纸立即重新渲染", foreground="#888888")
        self.status.grid(row=row + 1, column=0, columnspan=2, pady=(0, 8))

        # transient 只能绑到"可见"父窗：主窗隐藏时绑上去会让设置窗一起不显示
        if root.winfo_viewable():
            self.win.transient(root)
        self.win.deiconify()
        self.win.lift()
        try:
            self.win.focus_force()
        except Exception:
            pass

    def _save(self):
        def px_to_ratio(var, key, ratio_default, lo, hi):
            try:
                px = int(str(var.get()).strip())
            except ValueError:
                return  # 非法输入保留原值
            self.cfg[key] = max(lo, min(px, hi)) / self.screen_h

        px_to_ratio(self.title_px_var, "title_size_ratio", 0.075, 16, self.screen_h // 2)
        px_to_ratio(self.sub_px_var, "sub_size_ratio", 0.042, 12, self.screen_h // 2)
        px_to_ratio(self.tlg_var, "title_line_gap_ratio", 0.012, 0, 200)
        px_to_ratio(self.tsg_var, "title_sub_gap_ratio", 0.02, 0, 200)
        px_to_ratio(self.slg_var, "sub_line_gap_ratio", 0.014, 0, 200)
        label_to_file = {lb: f for lb, f in self._fonts}
        label_to_file[self._default_label] = None
        self.cfg["title_font_file"] = label_to_file.get(self.title_font_var.get())
        self.cfg["sub_font_file"] = label_to_file.get(self.sub_font_var.get())
        self.cfg["restore_on_quit"] = self.restore_var.get()
        self.cfg["vis_locked"] = self.lock_var.get()
        self.cfg["text_shadow"] = self.shadow_var.get()
        self.cfg["title_bold"] = self.tbold_var.get()
        self.cfg["sub_bold"] = self.sbold_var.get()
        self.cfg["title_overflow"] = "wrap" if self.title_of_var.get() == "换行" else "ellipsis"
        self.cfg["sub_overflow"] = "wrap" if self.sub_of_var.get() == "换行" else "ellipsis"
        self.cfg["title_color"] = self.title_color_var.get()
        self.cfg["sub_color"] = self.sub_color_var.get()
        try:
            self.cfg["vis_fps"] = max(10, min(120, int(self.fps_var.get())))
        except ValueError:
            pass  # 非法输入保留原值
        config.save(self.cfg)
        if set_autostart(self.autostart_var.get()) != self.autostart_var.get():
            self.status.config(text="自启动设置写入失败", foreground="#C0392B")
        else:
            self.status.config(text="已保存，壁纸正在重新渲染", foreground="#2E7D32")
