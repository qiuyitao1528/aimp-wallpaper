"""系统托盘图标：pystray 实现（纯 ctypes win32 后端）。

菜单动作不在托盘线程里碰 Tk，统一 root.after 调度回主线程。
"""
from __future__ import annotations

import os
import sys
import threading


def _load_image():
    from PIL import Image
    if getattr(sys, "frozen", False):  # PyInstaller COLLECT：icon.png 在 _MEIPASS 根
        path = os.path.join(sys._MEIPASS, "icon.png")
    else:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "assets", "icon.png")
    with Image.open(path) as im:
        return im.copy()


class Tray:
    def __init__(self, root, on_settings, on_toggle_vis, on_toggle_widget, on_toggle_lyrics, on_restore, on_quit):
        import pystray

        from . import applog

        def post(name, fn):
            applog.log(f"托盘动作: {name}")

            def run():
                try:
                    root.after(0, fn)
                except Exception:
                    applog.log_exc("托盘 after 调度异常:\n", *sys.exc_info())
            threading.Thread(target=run, daemon=True, name=f"tray-post-{name}").start()

        self._icon = pystray.Icon(
            "aimp-wallpaper", _load_image(), "AIMP Wallpaper",
            pystray.Menu(
                pystray.MenuItem("设置…", lambda: post("设置", on_settings), default=True),
                pystray.MenuItem("显示 / 隐藏频谱面板", lambda: post("开关可视化", on_toggle_vis)),
                pystray.MenuItem("显示 / 隐藏控件", lambda: post("开关控件", on_toggle_widget)),
                pystray.MenuItem("显示 / 隐藏歌词", lambda: post("开关歌词", on_toggle_lyrics)),
                pystray.MenuItem("恢复原壁纸", lambda: post("恢复原壁纸", on_restore)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", lambda: post("退出", on_quit)),
            ))
        threading.Thread(target=self._icon.run, daemon=True, name="tray").start()
        applog.log("托盘已创建")

    def stop(self):
        from . import applog
        applog.log("托盘停止")
        self._icon.stop()  # pystray stop 线程安全，主线程调用即可
