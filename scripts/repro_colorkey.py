# -*- coding: utf-8 -*-
"""最小复现：tk 窗口 + 色键分层 + 钉桌面层，看内容到底画没画出来。"""
import sys
import tkinter as tk

sys.path.insert(0, r"E:\aimp-wallpaper")
from PIL import Image, ImageDraw, ImageTk
from aimp_wallpaper import desktop

root = tk.Tk()
root.title("repro")
root.overrideredirect(True)
root.resizable(False, False)
W, H = 300, 120
c = tk.Canvas(root, width=W, height=H, bg=desktop.KEY_HEX, highlightthickness=0, bd=0)
c.pack()

img = Image.new("RGB", (W, H), desktop.KEY)
d = ImageDraw.Draw(img)
d.rounded_rectangle([1, 1, W - 2, H - 2], radius=14, fill=(24, 26, 34))
d.rounded_rectangle([1, 1, W - 2, H - 2], radius=14, outline=(60, 64, 80), width=1)
d.text((30, 50), "REPRO 卡片内容", fill=(242, 244, 248))
bg_img = ImageTk.PhotoImage(img)
c.create_image(0, 0, image=bg_img, anchor="nw", tags=("bg",))
c.create_rectangle(20, 80, 60, 100, fill="#FF3344", outline="", tags=("dbg",))
c.create_text(100, 90, text="红色矩形", fill="#FFFFFF", anchor="w")

root.geometry("+730+850")
root.update_idletasks()
root.update()  # 强制完成首次绘制
hwnd = desktop.user32.GetAncestor(desktop.HWND_T(root.winfo_id()), desktop.GA_ROOT)
desktop.style_desktop_widget(hwnd, 235)
desktop.pin_to_desktop(hwnd, 730, 850, W, H)
root.after(3000, root.destroy)
root.mainloop()
print("repro 完成")
