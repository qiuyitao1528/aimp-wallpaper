"""入口：uv run python -m aimp_wallpaper [restore]

restore 子命令：把首次运行前记录的原壁纸设回去。
"""
from __future__ import annotations

import atexit
import ctypes
import os
import sys
import threading
import tkinter as tk
from ctypes import wintypes

from . import applog, config, wallpaper
from .aimp_api import AimpIPC
from .tray import Tray
from .vis_panel import VisPanel


def _set_dpi_aware():
    """Per-Monitor V2：保证 GetMonitorRECT / 小部件拿到物理像素。"""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        user32.SetProcessDpiAwarenessContext.restype = wintypes_bool = ctypes.c_ssize_t
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        if not user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            raise OSError
    except OSError:
        try:
            user32.SetProcessDPIAware()
        except OSError:
            pass


def wallpaper_worker(ipc: AimpIPC, cfg: dict, stop: threading.Event):
    import comtypes
    comtypes.CoInitialize()  # COM 需在本线程初始化
    wallpaper.capture_original(cfg)
    last_gen = -1
    last_cover = None
    last_meta = None
    last_cfg_mtime = None

    def render(cover, meta, why: str) -> bool:
        try:
            paths = wallpaper.render_and_apply(cover, meta, cfg, wallpaper.get_monitors())
            applog.log(f"[{why}] 已更新 {len(paths)} 屏 "
                       f"字体: {cfg.get('title_font_file') or '默认'}/{cfg.get('sub_font_file') or '默认'}")
            return True
        except Exception:
            applog.log_exc(f"[{why}] 渲染失败:\n", *sys.exc_info())  # 失败不拖垮主程序
            return False

    while not stop.is_set():
        # 配置热重载：设置窗口保存后立即重渲染当前曲目
        try:
            mt = os.path.getmtime(config.CONFIG_PATH)
        except OSError:
            mt = None
        if last_cfg_mtime is None:
            last_cfg_mtime = mt
        elif mt != last_cfg_mtime:
            last_cfg_mtime = mt
            cfg.update(config.load())
            applog.log("配置变更，热重载")
            cover, meta = last_cover, last_meta
            if cover is None and meta is None:  # 本实例还没渲染过：取当前曲目兜底
                snap = ipc.snapshot()
                if (snap["title"] or snap["filename"]) and snap["connected"]:
                    cover = ipc.cover_now(snap["cover_gen"])
                    if cover is None:
                        cover = ipc.wait_cover(snap["cover_gen"], timeout=12.0)
                    meta = {k: snap[k] for k in ("title", "artist", "album")}
                    if cover is not None:
                        last_cover, last_meta, last_gen = cover, meta, snap["cover_gen"]
            if cover is not None or meta is not None:
                render(cover, meta, "热重载")
            else:
                applog.log("热重载：尚无曲目可渲染，跳过")

        gen = ipc.wait_track_change(timeout=0.5)
        if stop.is_set() or gen == last_gen or not ipc.snapshot()["connected"]:
            continue
        snap = ipc.snapshot()
        if not snap["title"] and not snap["filename"]:
            continue  # 元数据还没就绪，等下一轮
        cover = ipc.wait_cover(gen, timeout=12.0)  # 覆盖 10s 封面重试窗口
        if render(cover, snap, "切歌"):
            last_gen = gen
            last_cover, last_meta = cover, {k: snap[k] for k in ("title", "artist", "album")}


def _acquire_single_instance_mutex() -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW(None, False, "AIMP_Wallpaper_Single")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS（必须读 ctypes 缓存的 last error）


def _msgbox(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, text, "AIMP Wallpaper", 0x40)


def main():
    cfg = config.load()
    if len(sys.argv) > 1 and sys.argv[1].lower() == "restore":
        print(wallpaper.restore_original(cfg))
        return

    applog.init(os.path.join(cfg["output_dir"], "aimp-wallpaper.log"))

    if not _acquire_single_instance_mutex():
        applog.log("已有实例在运行，本次启动退出")
        _msgbox("AIMP Wallpaper 已在运行。")  # --windowed 静默退出会被当成没反应
        return

    applog.log("启动")
    sys.excepthook = lambda t, v, tb: applog.log_exc("未捕获异常:\n", t, v, tb)
    import gc
    gc.set_threshold(50_000, 100, 100)  # 动画循环：降低 GC 频率防微卡顿
    # 频谱动画时序：1ms 系统定时器分辨率 + 进程优先级提档，压 after 回调的调度迟到
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
        atexit.register(lambda: ctypes.windll.winmm.timeEndPeriod(1))
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(), 0x00008000)  # ABOVE_NORMAL_PRIORITY_CLASS
    except Exception:
        pass

    _set_dpi_aware()
    ipc = AimpIPC()
    ipc.start()
    stop = threading.Event()
    threading.Thread(target=wallpaper_worker, args=(ipc, cfg, stop), daemon=True, name="wallpaper").start()

    root = tk.Tk()
    root.title("AIMP Wallpaper")
    root.withdraw()  # 无可见主窗（界面=频谱面板+托盘）
    root.report_callback_exception = lambda t, v, tb: applog.log_exc("Tk 回调异常:\n", t, v, tb)

    panel = {"obj": None}

    def show_vis():
        applog.log("show_vis")
        if panel["obj"] is None:
            try:
                panel["obj"] = VisPanel(root, cfg)
            except Exception:
                applog.log_exc("VisPanel 创建失败:\n", *sys.exc_info())
                return
            if cfg.get("vis_hidden"):  # 隐藏状态下被托盘点开：状态归位
                cfg["vis_hidden"] = False
                config.save(cfg)
        else:
            panel["obj"].show()

    if not cfg.get("vis_hidden"):
        try:
            panel["obj"] = VisPanel(root, cfg)
        except Exception:
            applog.log_exc("启动建面板失败:\n", *sys.exc_info())

    def open_settings():
        from .settings_gui import SettingsWindow
        SettingsWindow(root, cfg)

    def toggle_vis():
        applog.log(f"toggle_vis: obj={panel['obj'] is not None} vis_hidden={cfg.get('vis_hidden')}")
        p = panel["obj"]
        if p is None or cfg.get("vis_hidden"):
            show_vis()
        else:
            p.hide()

    def restore_wp():
        def _do():
            import comtypes
            comtypes.CoInitialize()
            applog.log("手动恢复原壁纸: " + wallpaper.restore_original(cfg))
        threading.Thread(target=_do, daemon=True, name="restore").start()

    _real_destroy = root.destroy

    def _quit_app():
        """统一退出（托盘/小部件/面板三条路都汇到这）：按设置恢复原壁纸（最多等 3s）→ 停托盘 → 销毁 UI。"""
        applog.log("退出开始")
        if cfg.get("restore_on_quit", True):
            done = threading.Event()

            def _restore():
                try:
                    import comtypes
                    comtypes.CoInitialize()
                    applog.log("恢复原壁纸: " + wallpaper.restore_original(cfg))
                except Exception:
                    applog.log_exc("恢复原壁纸失败:\n", *sys.exc_info())
                finally:
                    done.set()
            threading.Thread(target=_restore, daemon=True, name="restore").start()
            done.wait(3.0)  # 恢复卡死也照样退，不留僵尸进程和僵尸图标
        try:
            tray.stop()
        except Exception:
            applog.log_exc("托盘停止失败:\n", *sys.exc_info())
        applog.log("销毁 UI")
        _real_destroy()

    root.destroy = _quit_app  # 兜住小部件/面板右键的退出路径
    tray = Tray(root, on_settings=open_settings, on_toggle_vis=toggle_vis,
                on_restore=restore_wp, on_quit=_quit_app)
    atexit.register(lambda: tray.stop())  # 崩溃退出时兜底收托盘图标
    gc.freeze()  # 启动期对象移入永久代，进一步降低运行期 GC 成本
    applog.log("进入 mainloop")
    try:
        root.mainloop()
    finally:
        stop.set()
        ipc.shutdown()
        applog.log("mainloop 退出，进程结束")


if __name__ == "__main__":
    main()
