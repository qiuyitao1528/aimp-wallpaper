# -*- coding: utf-8 -*-
"""淡入失败时写日志（不再静默）。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()
OLD = """            overlays = _fade.crossfade(layers, int(cfg.get("fade_ms", 220)))
        except Exception:
            overlays = []"""
NEW = """            overlays = _fade.crossfade(layers, int(cfg.get("fade_ms", 220)))
        except Exception:
            overlays = []  # 过渡失败就硬切，绝不影响换壁纸
            try:
                from . import applog
                applog.log_exc("淡入过渡失败（回退为直接切换）:\\n", *sys.exc_info())
            except Exception:
                pass"""
if "淡入过渡失败" in s:
    print("已有日志")
elif OLD in s:
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    print("已加失败日志")
else:
    print("未匹配")
