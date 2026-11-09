# -*- coding: utf-8 -*-
"""补回"背景模糊(像素)"设置项（v0.1.0 有，之前设置重写时丢失）。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\settings_gui.py"
s = io.open(P, encoding="utf-8").read()

if "blur_var" in s:
    print("已存在，跳过")
    raise SystemExit

# 1) 选项常量
s = s.replace(
    'GAP_CHOICES = [0, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40]',
    'GAP_CHOICES = [0, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40]\n'
    'BLUR_CHOICES = [8, 16, 24, 28, 32, 40, 56, 72, 100]')

# 2) 控件（放在字号之前）
s = s.replace(
    '        self.title_px_var, _, _ = px_row("歌名字号(像素)", "title_size_ratio", 0.075, SIZE_CHOICES, 16, self.screen_h // 2)',
    '''        # 背景模糊半径（像素，直接对应 blur_radius）
        ttk.Label(self.win, text="背景模糊(像素)").grid(row=row, column=0, sticky="w", **pad)
        blur_cur = int(cfg.get("blur_radius", 28))
        blur_values = [str(x) for x in BLUR_CHOICES]
        if str(blur_cur) not in blur_values:
            blur_values.insert(0, str(blur_cur))
        self.blur_var = tk.StringVar(value=str(blur_cur))
        ttk.Combobox(self.win, textvariable=self.blur_var, values=blur_values, width=8).grid(
            row=row, column=1, sticky="w", **pad)
        row += 1

        self.title_px_var, _, _ = px_row("歌名字号(像素)", "title_size_ratio", 0.075, SIZE_CHOICES, 16, self.screen_h // 2)''')

# 3) 保存
s = s.replace(
    '        self.cfg["title_size_ratio"] = self.title_var.get() / 1000.0',
    '        self.cfg["blur_radius"] = self.blur_var.get()')
if '"blur_radius"] = self.blur_var' not in s:
    # 兜底：插到 _save 里第一个 cfg 赋值前
    s = s.replace('    def _save(self):\n', '    def _save(self):\n'
                  '        try:\n'
                  '            self.cfg["blur_radius"] = max(4, min(200, int(str(self.blur_var.get()).strip())))\n'
                  '        except ValueError:\n'
                  '            pass\n', 1)
io.open(P, "w", encoding="utf-8").write(s)
print("已补回背景模糊设置")
