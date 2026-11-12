"""设置窗口：壁纸 / 封面 / 排版 / 歌名 / 歌手 / 专辑 / 歌曲信息 / 面板 / 系统 九个标签页。

归类：画面（壁纸/封面）→ 文字（排版+四行）→ 悬浮部件（面板）→ 系统。
每页相关选项用分组框（ttk.Labelframe）框起来，密集页用双列布局压短窗口。
结构：__init__ 只做窗口骨架；各页签由 _tab_* 方法构建（_group 建分组框）；
_save 按段落保存。新增控件：在对应 _tab_* 的分组框里加一行 _add_*，
并在 _save 对应段落补一行。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import colorchooser, ttk

from . import config

SIZE_CHOICES = [32, 40, 48, 56, 64, 72, 80, 96, 112, 128, 144, 160]
GAP_CHOICES = [0, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40]
BLUR_CHOICES = [8, 16, 24, 28, 32, 40, 56, 72, 100]
OFFSET_CHOICES = [-200, -150, -100, -60, -30, 0, 30, 60, 100, 150, 200]
SHADOW_OFFSET_CHOICES = [0, 8, 16, 24, 40, 60, 80, 120]  # 渲染端 max(4,·)，负值无效故不提供
SCALE_CHOICES = ["0.3", "0.5", "0.7", "0.8", "0.9", "1.0", "1.1", "1.2", "1.4", "1.6", "1.8", "2.0"]
FPS_CHOICES = ["15", "20", "24", "30", "45", "60", "90", "120"]
PCT_CHOICES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95]
ALIGN_ITEMS = [("左对齐", "left"), ("居中", "center"), ("右对齐", "right")]
VALIGN_ITEMS = [("顶部", "top"), ("居中", "center"), ("底部", "bottom")]
BG_CHOICES = [("高斯模糊", "blur"), ("模糊+暗角", "blur_vignette"),
              ("原图铺满", "sharp"), ("主色渐变", "gradient")]
BLUR_TYPE_ITEMS = [("高斯", "gauss"), ("柔焦", "soft"), ("雾面", "fog"), ("辉光", "glow")]
COVER_RADIUS_ITEMS = [("自动", 0), ("4", 4), ("8", 8), ("12", 12),
                      ("16", 16), ("24", 24), ("32", 32), ("48", 48)]
SHADOW_ALPHA_CHOICES = [0, 40, 70, 100, 130, 160, 200]
PAUSE_MODE_ITEMS = [("关", "off"), ("压暗", "darken"), ("角标", "badge"), ("压暗+角标", "both")]
PAUSE_SCOPE_ITEMS = [("整幅", "all"), ("仅背景", "bg")]
COVER_ANCHOR_ITEMS = [("左侧", "left"), ("右侧", "right"), ("居中", "center"), ("居中·左到线", "center_bound")]
OVERFLOW_ITEMS = [("换行", "wrap"), ("省略号", "ellipsis")]
SPACE_WRAP_ITEMS = [("关", "0"), ("2", "2"), ("3", "3"), ("4", "4"),
                    ("5", "5"), ("6", "6"), ("8", "8"), ("10", "10")]
STROKE_CHOICES = [0, 1, 2, 3, 4, 6]
COVER_STROKE_CHOICES = [0, 1, 2, 3, 4, 6, 8]
LYRICS_SIDE_ITEMS = [("面板下方", "below"), ("面板上方", "above")]
LYRICS_GAP_CHOICES = [0, 4, 6, 8, 10, 12, 16]
LYRICS_LANG_ITEMS = [("简体中文优先", "zh-Hans"), ("繁体中文优先", "zh-Hant"), ("不区分（取第一个）", "any")]
LYRICS_FOLLOW_ITEMS = [("跟随频谱面板", "panel"), ("跟随壁纸文字区", "anchor"), ("屏幕右下固定", "fixed")]
LYRICS_WIDTH_CHOICES = [280, 320, 420, 520, 640]
MARGIN_CHOICES = [4, 8, 10, 12, 16, 20, 24]
ANCHOR_GAP_CHOICES = [4, 8, 10, 14, 20]
LINE_ITEMS = (("title", "歌名"), ("artist", "歌手"), ("album", "专辑"), ("info", "歌曲信息"))
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
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True,
                           timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return os.path.exists(lnk)
        if os.path.exists(lnk):
            os.remove(lnk)
        return True
    except Exception:
        return False


def _luma(hex_color: str) -> int:
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
    _active = None  # 单例守卫：旧窗未关时再开，先销毁旧窗（避免双窗并发写同一配置）

    def __init__(self, root: tk.Tk, cfg: dict):
        cls = type(self)
        if cls._active is not None:
            try:
                if cls._active.winfo_exists():
                    cls._active.destroy()
            except Exception:
                pass
        cls._active = self.win = tk.Toplevel(root)
        self.cfg = cfg
        self.win.title("AIMP Wallpaper 设置")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self.win.after(1200, lambda: self.win.attributes("-topmost", False))
        self.screen_h = max(1, root.winfo_screenheight())
        self.screen_short = min(max(1, root.winfo_screenwidth()), self.screen_h)

        self._fonts = _available_fonts()
        self._file_to_label = {f: lb for lb, f in self._fonts}
        self._label_to_file = {lb: f for lb, f in self._fonts}
        self._default_label = "默认（微软雅黑）"
        self._label_to_file[self._default_label] = None
        self._invalid = []
        self._line_vars = {}

        nb = ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self._pages, self._rows = {}, {}
        # 页签按归类排序；四行文字各自一页，避免单页太长
        for name in ("壁纸", "封面", "排版", "歌名", "歌手", "专辑", "歌曲信息", "面板", "系统"):
            f = ttk.Frame(nb, padding=10)
            nb.add(f, text=name)
            self._pages[name] = f
            self._rows[f] = 0

        self._tab_wallpaper()
        self._tab_cover()
        self._tab_layout()
        for key, zh in LINE_ITEMS:
            self._tab_line(key, zh)
        self._refresh_order_labels()
        self._tab_panel()
        self._tab_system()

        ttk.Button(self.win, text="保存", command=self._save).pack(pady=8)
        self.status = ttk.Label(self.win, text="保存后壁纸立即重新渲染", foreground="#888888")
        self.status.pack(pady=(0, 8))
        self._status_job = None

        # 居中显示（多显示器下以主屏为基准）
        self.win.update_idletasks()
        sw, sh = self.win.winfo_width(), self.win.winfo_height()
        x = max(0, (root.winfo_screenwidth() - sw) // 2)
        y = max(0, (root.winfo_screenheight() - sh) // 3)
        self.win.geometry(f"+{x}+{y}")

        # transient 只能绑到"可见"父窗：主窗隐藏时绑上去会让设置窗一起不显示
        if root.winfo_viewable():
            self.win.transient(root)
        self.win.deiconify()
        self.win.lift()
        try:
            self.win.focus_force()
        except Exception:
            pass

    # ---------- 控件小工具 ----------

    def _two_col(self, pg):
        """双列布局：两列等宽。"""
        pg.columnconfigure(0, weight=1, uniform="col")
        pg.columnconfigure(1, weight=1, uniform="col")

    def _group(self, pg, title: str, col: int = 0, row: int = 0, colspan: int = 1):
        """分组框：相关选项框在一起，内部沿用 _rows 行计数（与页级同一套 _add_*）。"""
        g = ttk.Labelframe(pg, text=title, padding=(8, 4))
        g.grid(row=row, column=col, columnspan=colspan, sticky="new", padx=4, pady=(0, 8))
        self._rows[g] = 0
        return g

    def _add_widget(self, page, label, widget):
        r = self._rows[page]
        if label:
            ttk.Label(page, text=label).grid(row=r, column=0, sticky="w",
                                             padx=6, pady=3)
            widget.grid(row=r, column=1, sticky="w", padx=6, pady=3)
        else:
            widget.grid(row=r, column=0, columnspan=2, sticky="w", padx=6, pady=3)
        self._rows[page] = r + 1

    def _add_combo(self, page, label, values, current, width=8, readonly=False):
        var = tk.StringVar(value=str(current))
        vals = [str(v) for v in values]
        if str(current) not in vals:
            vals.insert(0, str(current))
        self._add_widget(page, label,
                         ttk.Combobox(page, textvariable=var, values=vals, width=width,
                                      state="readonly" if readonly else None))
        return var

    def _add_check(self, page, label, value):
        var = tk.BooleanVar(value=bool(value))
        self._add_widget(page, None, ttk.Checkbutton(page, text=label, variable=var))
        return var

    def _add_labeled(self, page, label, mapping, current, width=10):
        var = tk.StringVar(value={v: k for k, v in mapping}.get(current, mapping[0][0]))
        self._add_widget(page, label,
                         ttk.Combobox(page, textvariable=var, values=[k for k, _ in mapping],
                                      state="readonly", width=width))
        return var

    def _px_of(self, key, ratio_default):
        # 与渲染口径一致：几何比例基于宽高较小者（wallpaper.py 的 dim）
        return int(self.screen_short * float(self.cfg.get(key, ratio_default)))

    def _add_color(self, page, label, key, default):
        raw = str(self.cfg.get(key, default) or default).upper()
        var = tk.StringVar(value=raw)

        def _apply(color):
            try:
                btn.configure(bg=color, fg="#000000" if _luma(color) > 140 else "#FFFFFF")
                return True
            except tk.TclError:  # 配置文件里的非法颜色值：回退默认，避免整个窗口打不开
                var.set(default.upper())
                btn.configure(bg=default, fg="#000000" if _luma(default) > 140 else "#FFFFFF")
                return False

        def pick():
            _rgb, hexv = colorchooser.askcolor(color=var.get(), parent=self.win, title=label)
            if hexv:
                var.set(str(hexv).upper())
                _apply(var.get())

        btn = tk.Button(page, textvariable=var, relief="groove", width=10, command=pick)
        if not _apply(var.get()):
            var.set(default.upper())
        self._add_widget(page, label, btn)
        return var

    def _set_status(self, text: str, color: str = "#2E7D32", sticky: bool = False):
        if getattr(self, "_status_job", None):
            try:
                self.win.after_cancel(self._status_job)
            except Exception:
                pass
            self._status_job = None
        self.status.config(text=text, foreground=color)
        if not sticky:  # 绿色提示 3 秒后回到默认文案；红色警告保留到下一次操作
            self._status_job = self.win.after(
                3000, lambda: self.status.config(text="保存后壁纸立即重新渲染", foreground="#888888"))

    # ---------- 壁纸页（背景 / 过渡 / 日夜 / 暂停） ----------

    def _add_pct_invert(self, page, label, key, choices, keep):
        """darken 特例：GUI 显示「压暗百分比」，配置存保留亮度 darken = 1 - pct/100。"""
        pct = round((1.0 - float(keep or 0.75)) * 100)
        return self._add_combo(page, label, choices, pct)

    def _tab_wallpaper(self):
        cfg, pg = self.cfg, self._pages["壁纸"]
        self._two_col(pg)
        g_bg = self._group(pg, "背景与模糊", col=0)
        self.bg_style_var = self._add_labeled(g_bg, "背景方案", BG_CHOICES, cfg.get("bg_style", "blur"))
        self.blur_type_var = self._add_labeled(g_bg, "模糊类型", BLUR_TYPE_ITEMS,
                                               cfg.get("blur_type", "gauss"))
        self.blur_var = self._add_combo(g_bg, "模糊强度(像素)", BLUR_CHOICES,
                                        int(cfg.get("blur_radius", 28)))
        self.darken_var = self._add_pct_invert(g_bg, "背景压暗(%)", "darken", PCT_CHOICES,
                                               float(cfg.get("darken", 0.75) or 0.75))
        self.fade_native_var = self._add_check(
            g_bg, "壁纸过渡（Windows 原生淡入；系统本身已有过渡可关闭）", cfg.get("fade_native", True))
        g_night = self._group(pg, "日/夜主题", col=1, row=0)
        self.night_var = self._add_check(g_night, "跟随系统日/夜主题（夜间叠黑色遮罩）",
                                         cfg.get("theme_night_follow", False))
        self.night_alpha_var = self._add_combo(g_night, "夜间遮罩浓度(%)", PCT_CHOICES,
                                               int(cfg.get("night_overlay", 30) or 30))
        g_pause = self._group(pg, "暂停反馈", col=1, row=1)
        self.pause_mode_var = self._add_labeled(g_pause, "暂停显示", PAUSE_MODE_ITEMS,
                                                cfg.get("pause_mode", "darken"))
        self.pause_dark_var = self._add_combo(g_pause, "暂停压暗浓度(%)", PCT_CHOICES,
                                              int(cfg.get("pause_darken", 30) or 30))
        self.pause_scope_var = self._add_labeled(g_pause, "压暗范围", PAUSE_SCOPE_ITEMS,
                                                 cfg.get("pause_darken_scope", "all"))
        self.pause_shrink_var = self._add_check(g_pause, "暂停时封面缩小", cfg.get("pause_shrink", False))
        self.pause_shrink_pct_var = self._add_combo(g_pause, "封面缩小幅度(%)", [5, 8, 10, 15, 20],
                                                    int(cfg.get("pause_shrink_pct", 8) or 8))

    # ---------- 封面页 ----------

    def _tab_cover(self):
        cfg, pg = self.cfg, self._pages["封面"]
        self._two_col(pg)
        g_geo = self._group(pg, "大小与位置", col=0)
        self.cover_anchor_var = self._add_labeled(g_geo, "缩放基准", COVER_ANCHOR_ITEMS,
                                                  cfg.get("cover_anchor", "left"))
        self.cover_scale_var = self._add_combo(g_geo, "封面大小(倍率)", SCALE_CHOICES,
                                               cfg.get("cover_scale", 1.0) or 1.0)
        self.cover_dx_var = self._add_combo(g_geo, "封面 X 偏移(像素)", OFFSET_CHOICES,
                                            int(cfg.get("cover_offset_x", 0) or 0))
        self.cover_dy_var = self._add_combo(g_geo, "封面 Y 偏移(像素)", OFFSET_CHOICES,
                                            int(cfg.get("cover_offset_y", 0) or 0))
        self.cover_margin_var = self._add_combo(g_geo, "封面左边距(%)", MARGIN_CHOICES,
                                                round(float(cfg.get("cover_margin_ratio", 0.12)
                                                             or 0.12) * 100), readonly=True)
        g_look = self._group(pg, "圆角·阴影·描边", col=1)
        self.cover_radius_var = self._add_labeled(g_look, "封面圆角(像素)", COVER_RADIUS_ITEMS,
                                                  int(cfg.get("cover_radius", 0) or 0))
        self.cover_sa_var = self._add_combo(g_look, "封面阴影浓度", SHADOW_ALPHA_CHOICES,
                                            int(cfg.get("cover_shadow_alpha", 130) or 0))
        self.cover_so_var = self._add_combo(g_look, "封面阴影偏移(像素)", SHADOW_OFFSET_CHOICES,
                                            int(cfg.get("cover_shadow_offset", 40) or 40))
        self.cover_sw_var = self._add_combo(g_look, "封面描边宽(像素)", COVER_STROKE_CHOICES,
                                            int(cfg.get("cover_stroke_w", 0) or 0))
        self.cover_sc_var = self._add_color(g_look, "封面描边色", "cover_stroke_color", "#000000")

    # ---------- 行页（歌名/歌手/专辑/歌曲信息 各自一页） ----------

    def _tab_line(self, key: str, zh: str):
        cfg, pg = self.cfg, self._pages[zh]
        self._two_col(pg)
        v = {}
        # 左上：显示与顺序
        g_show = self._group(pg, "显示与顺序", col=0, row=0)
        v["order_lbl"] = ttk.Label(g_show, text="", foreground="#4C8BF5")
        self._add_widget(g_show, "当前顺序", v["order_lbl"])
        v["show"] = self._add_check(g_show, "显示这一行", cfg.get(f"{key}_show", True))
        # 行顺序：上移/下移按钮（改 line_order，保存即按新顺序重渲染）
        f_btns = ttk.Frame(g_show)
        ttk.Button(f_btns, text="上移 ↑", width=7,
                   command=lambda k=key: self._move_line(k, -1)).pack(side="left", padx=(0, 6))
        ttk.Button(f_btns, text="下移 ↓", width=7,
                   command=lambda k=key: self._move_line(k, 1)).pack(side="left")
        self._add_widget(g_show, "行顺序", f_btns)
        # 右上：字体与字号
        g_font = self._group(pg, "字体与字号", col=1, row=0)
        v["size"] = self._add_combo(g_font, "字号(像素)", SIZE_CHOICES,
                                    self._px_of(f"{key}_size_ratio",
                                                0.075 if key == "title" else 0.042))
        v["font"] = self._add_combo(g_font, "字体",
                                    [self._default_label] + [lb for lb, _ in self._fonts],
                                    self._file_to_label.get(cfg.get(f"{key}_font_file"),
                                                            self._default_label),
                                    width=28, readonly=True)
        v["bold"] = self._add_check(g_font, "加粗", cfg.get(f"{key}_bold", key == "title"))
        # 左下：颜色与效果
        g_fx = self._group(pg, "颜色与效果", col=0, row=1)
        v["color"] = self._add_color(g_fx, "颜色", f"{key}_color", "#FFFFFF")
        v["shadow"] = self._add_check(g_fx, "阴影", cfg.get(f"{key}_shadow", True))
        v["stroke_w"] = self._add_combo(g_fx, "描边宽(像素)", STROKE_CHOICES,
                                        int(cfg.get(f"{key}_stroke_w", 0) or 0))
        v["stroke_color"] = self._add_color(g_fx, "描边色", f"{key}_stroke_color", "#000000")
        # 右下：过长与断行
        g_of = self._group(pg, "过长与断行", col=1, row=1)
        v["of"] = self._add_labeled(g_of, "过长", OVERFLOW_ITEMS,
                                    cfg.get(f"{key}_overflow",
                                            "wrap" if key == "title" else "ellipsis"))
        v["space_w"] = self._add_labeled(g_of, "空格断行(字符)", SPACE_WRAP_ITEMS,
                                         str(int(cfg.get(f"{key}_space_window", 5) or 0)))
        self._line_vars[key] = v
        if key == "info":  # 歌曲信息页底部通栏：展示模板（token 见 config 注释）
            g_tpl = self._group(pg, "歌曲信息模板", col=0, row=2, colspan=2)
            self._info_tpl_var = tk.StringVar(value=str(self.cfg.get(
                "info_template", "{format} {samplerate} {bitrate} {bits}")))
            self._add_widget(g_tpl, "模板",
                             ttk.Entry(g_tpl, textvariable=self._info_tpl_var, width=34))

    # ---------- 排版页 ----------

    def _tab_layout(self):
        cfg, pg = self.cfg, self._pages["排版"]
        self._two_col(pg)
        g_gap = self._group(pg, "总开关与行间距", col=0)
        self.show_text_var = self._add_check(g_gap, "显示文字内容（总开关）", cfg.get("show_text", True))
        self.tsg_var = self._add_combo(g_gap, "歌名行后间距(像素)", GAP_CHOICES,
                                       self._px_of("title_sub_gap_ratio", 0.02))
        self.tlg_var = self._add_combo(g_gap, "歌名折行间距(像素)", GAP_CHOICES,
                                       self._px_of("title_line_gap_ratio", 0.012))
        self.slg_var = self._add_combo(g_gap, "歌手/专辑/信息行间距(像素)", GAP_CHOICES,
                                       self._px_of("sub_line_gap_ratio", 0.014))
        g_pos = self._group(pg, "位置与对齐", col=1)
        self.text_dx_var = self._add_combo(g_pos, "文字 X 偏移(像素)", OFFSET_CHOICES,
                                           int(cfg.get("text_offset_x", 0) or 0))
        self.text_dy_var = self._add_combo(g_pos, "文字 Y 偏移(像素)", OFFSET_CHOICES,
                                           int(cfg.get("text_offset_y", 0) or 0))
        self.text_align_var = self._add_labeled(g_pos, "文字水平对齐", ALIGN_ITEMS,
                                                cfg.get("text_align", "left"))
        self.text_valign_var = self._add_labeled(g_pos, "文字垂直对齐", VALIGN_ITEMS,
                                                 cfg.get("text_valign", "center"))

    # ---------- 面板页（频谱 + 歌词） ----------

    def _tab_panel(self):
        cfg, pg = self.cfg, self._pages["面板"]
        self._two_col(pg)
        # 左列：频谱面板 + 歌词窗位置
        g_vis = self._group(pg, "频谱面板", col=0, row=0)
        self.vis_show_var = self._add_check(g_vis, "显示频谱面板", not cfg.get("vis_hidden", False))
        self.vis_w_var = self._add_combo(g_vis, "面板宽度(像素)", [280, 320, 420, 520, 640],
                                         int(cfg.get("vis_width", 420) or 420), readonly=True)
        self.vis_h_var = self._add_combo(g_vis, "面板高度(像素)", [80, 100, 120, 160, 200],
                                         int(cfg.get("vis_height", 120) or 120), readonly=True)
        self.fps_var = self._add_combo(g_vis, "刷新率(FPS)", FPS_CHOICES,
                                       int(cfg.get("vis_fps", 30) or 30))
        self.lock_var = self._add_check(g_vis, "锁定频谱面板（禁拖动，仍跟随壁纸）", cfg.get("vis_locked"))
        self.vis_gap_var = self._add_combo(g_vis, "面板与文字区间距(像素)", ANCHOR_GAP_CHOICES,
                                           int(cfg.get("vis_anchor_gap", 10) or 10))
        g_lyr_pos = self._group(pg, "歌词窗·位置与显示", col=0, row=1)
        self.lyr_show_var = self._add_check(g_lyr_pos, "显示歌词", not cfg.get("lyrics_hidden", False))
        self.lyr_follow_var = self._add_labeled(g_lyr_pos, "歌词跟随", LYRICS_FOLLOW_ITEMS,
                                                cfg.get("lyrics_follow", "panel"))
        self.lyr_w_var = self._add_combo(g_lyr_pos, "歌词窗宽度(像素)", LYRICS_WIDTH_CHOICES,
                                         int(cfg.get("lyrics_width", 420) or 420), readonly=True)
        self.lyr_side_var = self._add_labeled(g_lyr_pos, "歌词位置", LYRICS_SIDE_ITEMS,
                                              cfg.get("lyrics_side", "below"))
        self.lyr_gap_var = self._add_combo(g_lyr_pos, "歌词间距(像素)", LYRICS_GAP_CHOICES,
                                           int(cfg.get("lyrics_gap", 6) or 6))
        self.lyr_lock_var = self._add_check(g_lyr_pos, "锁定歌词窗（禁拖动，仍跟随壁纸）",
                                            cfg.get("lyrics_locked", False))
        # 右列：歌词窗内容 + 样式
        g_lyr_ct = self._group(pg, "歌词窗·内容", col=1, row=0)
        self.lyr_lang_var = self._add_labeled(g_lyr_ct, "歌词多语言优先", LYRICS_LANG_ITEMS,
                                              cfg.get("lyrics_lang_pref", "zh-Hans"))
        self.lyr_trans_var = self._add_check(g_lyr_ct, "显示当前行译文", cfg.get("lyrics_show_trans", True))
        self.lyr_next_var = self._add_check(g_lyr_ct, "显示下一行原文", cfg.get("lyrics_show_next", True))
        g_lyr_fx = self._group(pg, "歌词窗·样式", col=1, row=1)
        self.lyr_font_var = self._add_combo(g_lyr_fx, "歌词字体",
                                            [self._default_label] + [lb for lb, _ in self._fonts],
                                            self._file_to_label.get(cfg.get("lyrics_font_file"),
                                                                    self._default_label),
                                            width=28, readonly=True)
        self.lyr_px_var = self._add_combo(g_lyr_fx, "歌词字号(像素)", SIZE_CHOICES,
                                          self._px_of("lyrics_size_ratio", 0.032))
        self.lyr_color_var = self._add_color(g_lyr_fx, "歌词颜色", "lyrics_color", "#FFFFFF")
        self.lyr_next_color_var = self._add_color(g_lyr_fx, "下一行颜色", "lyrics_next_color", "#B0B0B0")
        self.lyr_sw_var = self._add_combo(g_lyr_fx, "歌词描边宽(像素)", STROKE_CHOICES,
                                          int(cfg.get("lyrics_stroke_w", 2) or 0))
        self.lyr_sc_var = self._add_color(g_lyr_fx, "歌词描边色", "lyrics_stroke_color", "#000000")
        self.lyr_shadow_var = self._add_check(g_lyr_fx, "歌词阴影", cfg.get("lyrics_shadow", True))

    # ---------- 系统页 ----------

    def _tab_system(self):
        cfg, pg = self.cfg, self._pages["系统"]
        g = self._group(pg, "常规")
        self.autostart_var = self._add_check(g, "开机自启动", autostart_enabled())
        self.restore_var = self._add_check(g, "退出时恢复原壁纸", cfg.get("restore_on_quit", True))

    def _int(self, var, key, lo, hi, ratio=False, label=""):
        try:
            v = int(str(var.get()).strip())
        except (TypeError, ValueError):
            if label:
                self._invalid.append(label)
            return
        self.cfg[key] = max(lo, min(v, hi)) / self.screen_short if ratio else max(lo, min(v, hi))

    def _float(self, var, key, lo, hi, label=""):
        try:
            v = float(str(var.get()).strip())
        except (TypeError, ValueError):
            if label:
                self._invalid.append(label)
            return
        self.cfg[key] = max(lo, min(v, hi))

    def _refresh_order_labels(self):
        """把当前行顺序（如 1歌名 2歌手 …）显示到四个行页的指示条上。"""
        zh_of = dict(LINE_ITEMS)
        default = [k for k, _z in LINE_ITEMS]
        order = [g for g in (self.cfg.get("line_order") or default) if g in default]
        for g in default:
            if g not in order:
                order.append(g)
        text = "  →  ".join(f"{i + 1}.{zh_of[g]}" for i, g in enumerate(order))
        for key, v in self._line_vars.items():
            v["order_lbl"].configure(text=text)

    def _move_line(self, key: str, delta: int):
        """右侧文字行顺序上移/下移：改 line_order 并保存，壁纸立即按新顺序重渲染。"""
        default = ["title", "artist", "album", "info"]
        order = [g for g in (self.cfg.get("line_order") or default) if g in default]
        for g in default:
            if g not in order:
                order.append(g)
        if key not in order:
            return
        i = order.index(key)
        j = i + delta
        if not 0 <= j < len(order):
            self._set_status("已经在顶部/底部", "#888888", sticky=True)
            return
        order[i], order[j] = order[j], order[i]
        self.cfg["line_order"] = order
        config.save(self.cfg)
        self._refresh_order_labels()
        self._set_status("行顺序已更新")

    def _save(self):
        self._invalid = []
        self._save_wallpaper()
        self._save_cover()
        for key, v in self._line_vars.items():
            zh = dict(LINE_ITEMS)[key]
            self._int(v["size"], f"{key}_size_ratio", 8, self.screen_short, ratio=True,
                      label=f"{zh}字号")
            self._int(v["stroke_w"], f"{key}_stroke_w", 0, 6, label=f"{zh}描边宽")
            self.cfg[f"{key}_font_file"] = self._label_to_file.get(v["font"].get())
            self.cfg[f"{key}_color"] = v["color"].get()
            self.cfg[f"{key}_bold"] = v["bold"].get()
            self.cfg[f"{key}_shadow"] = v["shadow"].get()
            self.cfg[f"{key}_show"] = v["show"].get()
            self.cfg[f"{key}_overflow"] = dict(OVERFLOW_ITEMS).get(v["of"].get(),
                                                                   "wrap" if key == "title" else "ellipsis")
            self.cfg[f"{key}_space_window"] = int(dict(SPACE_WRAP_ITEMS).get(v["space_w"].get(), "5"))
            self.cfg[f"{key}_stroke_color"] = v["stroke_color"].get()
        self.cfg["info_template"] = self._info_tpl_var.get().strip() \
            or "{format} {samplerate} {bitrate} {bits}"
        self._int(self.tsg_var, "title_sub_gap_ratio", 0, 300, ratio=True, label="歌名行后间距")
        self._int(self.tlg_var, "title_line_gap_ratio", 0, 300, ratio=True, label="歌名折行间距")
        self._int(self.slg_var, "sub_line_gap_ratio", 0, 300, ratio=True, label="行间距")
        self._int(self.text_dx_var, "text_offset_x", -2000, 2000, label="文字 X 偏移")
        self._int(self.text_dy_var, "text_offset_y", -2000, 2000, label="文字 Y 偏移")
        self._int(self.fps_var, "vis_fps", 10, 120, label="刷新率")
        self._int(self.vis_gap_var, "vis_anchor_gap", 0, 100, label="面板与文字区间距")
        self.cfg["show_text"] = self.show_text_var.get()
        self.cfg["lyrics_hidden"] = not self.lyr_show_var.get()
        self.cfg["lyrics_locked"] = self.lyr_lock_var.get()
        self.cfg["lyrics_follow"] = dict(LYRICS_FOLLOW_ITEMS).get(self.lyr_follow_var.get(), "panel")
        self.cfg["lyrics_side"] = dict(LYRICS_SIDE_ITEMS).get(self.lyr_side_var.get(), "below")
        self._int(self.lyr_w_var, "lyrics_width", 200, 1000, label="歌词窗宽度")
        self._int(self.lyr_gap_var, "lyrics_gap", 0, 100, label="歌词间距")
        self.cfg["lyrics_lang_pref"] = dict(LYRICS_LANG_ITEMS).get(self.lyr_lang_var.get(), "zh-Hans")
        self.cfg["lyrics_show_trans"] = self.lyr_trans_var.get()
        self.cfg["lyrics_show_next"] = self.lyr_next_var.get()
        self.cfg["lyrics_font_file"] = self._label_to_file.get(self.lyr_font_var.get())
        self._int(self.lyr_px_var, "lyrics_size_ratio", 10, self.screen_short, ratio=True,
                  label="歌词字号")
        self.cfg["lyrics_color"] = self.lyr_color_var.get()
        self.cfg["lyrics_next_color"] = self.lyr_next_color_var.get()
        self._int(self.lyr_sw_var, "lyrics_stroke_w", 0, 6, label="歌词描边宽")
        self.cfg["lyrics_stroke_color"] = self.lyr_sc_var.get()
        self.cfg["lyrics_shadow"] = self.lyr_shadow_var.get()

        self.cfg["text_align"] = dict(ALIGN_ITEMS).get(self.text_align_var.get(), "left")
        self.cfg["text_valign"] = dict(VALIGN_ITEMS).get(self.text_valign_var.get(), "center")
        self.cfg["vis_locked"] = self.lock_var.get()
        self.cfg["vis_hidden"] = not self.vis_show_var.get()
        self._int(self.vis_w_var, "vis_width", 200, 1000, label="面板宽度")
        self._int(self.vis_h_var, "vis_height", 60, 400, label="面板高度")
        self.cfg["restore_on_quit"] = self.restore_var.get()
        config.save(self.cfg)

        # 自启动：只在勾选状态相对现状有变化时才写（避免每次保存都弹 PowerShell 窗口）
        want_autostart = self.autostart_var.get()
        if want_autostart != autostart_enabled() and not set_autostart(want_autostart):
            self._set_status("自启动设置写入失败", "#C0392B", sticky=True)
        elif self._invalid:
            self._set_status("已保存；以下数值无效已忽略：" + "、".join(self._invalid), "#C0392B", sticky=True)
        else:
            self._set_status("已保存，壁纸正在重新渲染")

    # ---------- 各页保存段 ----------

    def _save_wallpaper(self):
        self.cfg["bg_style"] = dict(BG_CHOICES).get(self.bg_style_var.get(), "blur")
        self.cfg["blur_type"] = dict(BLUR_TYPE_ITEMS).get(self.blur_type_var.get(), "gauss")
        self._int(self.blur_var, "blur_radius", 4, 200, label="模糊强度")
        # 背景压暗：GUI 是压暗百分比，darken=保留亮度（0.05~1.0）
        try:
            pct = max(0, min(95, int(str(self.darken_var.get()).strip())))
            self.cfg["darken"] = round(1.0 - pct / 100, 2)
        except (TypeError, ValueError):
            self._invalid.append("背景压暗")
        self.cfg["theme_night_follow"] = self.night_var.get()
        self._int(self.night_alpha_var, "night_overlay", 0, 95, label="夜间遮罩浓度")
        self.cfg["fade_native"] = self.fade_native_var.get()
        self.cfg["pause_mode"] = dict(PAUSE_MODE_ITEMS).get(self.pause_mode_var.get(), "darken")
        self._int(self.pause_dark_var, "pause_darken", 0, 95, label="暂停压暗浓度")
        self.cfg["pause_darken_scope"] = dict(PAUSE_SCOPE_ITEMS).get(self.pause_scope_var.get(), "all")
        self.cfg["pause_shrink"] = self.pause_shrink_var.get()
        self._int(self.pause_shrink_pct_var, "pause_shrink_pct", 0, 50, label="封面缩小幅度")

    def _save_cover(self):
        self.cfg["cover_anchor"] = dict(COVER_ANCHOR_ITEMS).get(self.cover_anchor_var.get(), "left")
        self._float(self.cover_scale_var, "cover_scale", 0.3, 2.0, label="封面大小")
        self._int(self.cover_dx_var, "cover_offset_x", -2000, 2000, label="封面 X 偏移")
        self._int(self.cover_dy_var, "cover_offset_y", -2000, 2000, label="封面 Y 偏移")
        try:
            mpct = max(2, min(30, int(str(self.cover_margin_var.get()).strip())))
            self.cfg["cover_margin_ratio"] = mpct / 100
        except (TypeError, ValueError):
            self._invalid.append("封面左边距")
        self.cfg["cover_radius"] = dict(COVER_RADIUS_ITEMS).get(self.cover_radius_var.get(), 0)
        self._int(self.cover_sa_var, "cover_shadow_alpha", 0, 255, label="封面阴影浓度")
        self._int(self.cover_so_var, "cover_shadow_offset", 0, 300, label="封面阴影偏移")
        self._int(self.cover_sw_var, "cover_stroke_w", 0, 8, label="封面描边宽")
        self.cfg["cover_stroke_color"] = self.cover_sc_var.get()
