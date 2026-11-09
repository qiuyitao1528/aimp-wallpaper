# -*- coding: utf-8 -*-
"""修：设置窗口在父窗隐藏时不显示（transient + withdraw 主窗）。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\settings_gui.py"
s = io.open(P, encoding="utf-8").read()
OLD = "        self.win.transient(root)\n"
NEW = """        # transient 只能绑到"可见"父窗：主窗隐藏时绑上去会让设置窗一起不显示
        if root.winfo_viewable():
            self.win.transient(root)
        self.win.deiconify()
        self.win.lift()
        try:
            self.win.focus_force()
        except Exception:
            pass
"""
if OLD in s:
    s = s.replace(OLD, NEW)
    io.open(P, "w", encoding="utf-8").write(s)
    print("已修补 settings_gui.py")
elif "winfo_viewable" in s:
    print("已修补过")
else:
    print("未找到目标行，需人工检查")
