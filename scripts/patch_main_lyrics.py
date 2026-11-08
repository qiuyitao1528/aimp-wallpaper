# -*- coding: utf-8 -*-
"""给 __main__.py 接入歌词窗口与抓取线程（幂等）。"""
import io

p = r"E:\aimp-wallpaper\aimp_wallpaper\__main__.py"
s = io.open(p, encoding="utf-8").read()

if "LyricsWindow" in s:
    print("已接入，跳过")
    raise SystemExit

s = s.replace(
    "from . import applog, config, wallpaper\nfrom .aimp_api import AimpIPC\nfrom .tray import Tray",
    "from . import applog, config, wallpaper\nfrom .aimp_api import AimpIPC\n"
    "from .lyrics import LyricsFetcher, LyricsWindow\nfrom .tray import Tray")

s = s.replace(
    '    panel = {"obj": None}\n',
    '    panel = {"obj": None}\n    lyrics = {"obj": None}\n')

s = s.replace(
    """    def toggle_widget():
        cfg["widget_hidden"] = not bool(cfg.get("widget_hidden"))
        config.save(cfg)
        applog.log(f"控件显隐切换: widget_hidden={cfg.get('widget_hidden')}")
""",
    """    def toggle_widget():
        cfg["widget_hidden"] = not bool(cfg.get("widget_hidden"))
        config.save(cfg)
        applog.log(f"控件显隐切换: widget_hidden={cfg.get('widget_hidden')}")

    def toggle_lyrics():
        cfg["lyrics_hidden"] = not bool(cfg.get("lyrics_hidden"))
        config.save(cfg)
        applog.log(f"歌词显隐切换: lyrics_hidden={cfg.get('lyrics_hidden')}")

    def get_panel_pos():
        p = panel["obj"]
        if p is not None and not cfg.get("vis_hidden"):
            try:
                return p._screen_pos()
            except Exception:
                return None
        return None
""")

s = s.replace(
    """    tray = Tray(root, on_settings=open_settings, on_toggle_vis=toggle_vis,
                on_toggle_widget=toggle_widget, on_restore=restore_wp, on_quit=_quit_app)
""",
    """    lyrics["obj"] = LyricsWindow(root, ipc, cfg, get_panel_pos)
    LyricsFetcher(ipc, cfg, lambda lines: lyrics["obj"].set_lines(lines)).start()

    tray = Tray(root, on_settings=open_settings, on_toggle_vis=toggle_vis,
                on_toggle_widget=toggle_widget, on_toggle_lyrics=toggle_lyrics,
                on_restore=restore_wp, on_quit=_quit_app)
""")

io.open(p, "w", encoding="utf-8").write(s)
print("patched")
