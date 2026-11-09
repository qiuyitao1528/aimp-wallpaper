# -*- coding: utf-8 -*-
"""修：关闭自启动时误报"设置失败"（set_autostart 返回成功与否，不该跟勾选状态比）。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\settings_gui.py"
s = io.open(P, encoding="utf-8").read()
OLD = """        if set_autostart(self.autostart_var.get()) != self.autostart_var.get():
            self.status.config(text="自启动设置写入失败", foreground="#C0392B")"""
NEW = """        if not set_autostart(self.autostart_var.get()):
            self.status.config(text="自启动设置写入失败", foreground="#C0392B")"""
if OLD in s:
    s = s.replace(OLD, NEW)
    io.open(P, "w", encoding="utf-8").write(s)
    print("已修 settings_gui.py 自启动判断")
else:
    print("未找到目标代码")
