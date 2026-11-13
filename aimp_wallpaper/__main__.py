"""入口：uv run python -m aimp_wallpaper [restore]

restore 子命令：把首次运行前记录的原壁纸设回去。
"""
from __future__ import annotations

import atexit
import ctypes
import os
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes

from . import applog, config, wallpaper
from .aimp_api import AimpIPC
from .lyrics import LyricsFetcher, LyricsWindow
from .tray import Tray
from .vis_panel import VisPanel


def _set_dpi_aware():
    """Per-Monitor V2：保证 GetMonitorRECT / 小部件拿到物理像素。"""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        user32.SetProcessDpiAwarenessContext.restype = ctypes.c_ssize_t
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
    # 跨轮状态（传给 _worker_round）：曲目代数/封面/元数据/配置mtime/主题基线/暂停基线
    state = {"gen": -1, "cover": None, "meta": None, "cfg_mtime": None,
             "dark": None, "dark_t": 0.0, "paused": False}

    def render(cover, meta, why: str) -> bool:
        try:
            # 暂停反馈在渲染时实时判定（pause_mode 开且未在播放），所有渲染路径统一
            paused = (cfg.get("pause_mode", "off") != "off"
                      and ipc.snapshot().get("state") != 2)
            # 所有重渲染（切歌/暂停/主题/热重载）都走过渡，是否淡入由 fade_native 决定
            paths = wallpaper.render_and_apply(cover, meta, cfg, wallpaper.get_monitors(),
                                               paused=paused)
            applog.log(f"[{why}] 已更新 {len(paths)} 屏 "
                       f"字体: {cfg.get('title_font_file') or '默认'}/{cfg.get('sub_font_file') or '默认'}")
            return True
        except Exception:
            applog.log_exc(f"[{why}] 渲染失败:\n", *sys.exc_info())  # 失败不拖垮主程序
            return False

    while not stop.is_set():
        # 整个循环体兜底：任何一轮的意外异常（配置解析/COM 抖动等）都不允许弄死
        # 壁纸线程——线程一死就永久不换壁纸，只能重启程序（用户实际遇到的顽疾）。
        try:
            _worker_round(ipc, cfg, stop, render, state)
        except Exception:
            applog.log_exc("壁纸线程单轮异常（已跳过本轮继续）:\n", *sys.exc_info())
            time.sleep(0.5)


def _worker_round(ipc, cfg, stop, render, state: dict):
    """壁纸线程的一轮：配置热重载 / 主题跟随 / 暂停反馈 / 切歌检测与渲染。

    state 携带跨轮状态：gen/cover/meta/cfg_mtime/dark/dark_t/paused。
    """
    last_gen = state["gen"]
    last_cover = state["cover"]
    last_meta = state["meta"]

    # 配置热重载：设置窗口保存后立即重渲染当前曲目
    try:
        mt = os.path.getmtime(config.CONFIG_PATH)
    except OSError:
        mt = None
    if state["cfg_mtime"] is None:
        state["cfg_mtime"] = mt
    elif mt != state["cfg_mtime"]:
        state["cfg_mtime"] = mt
        cfg.update(config.load())
        applog.log("配置变更，热重载")
        cover, meta = last_cover, last_meta
        if cover is None and meta is None:  # 本实例还没渲染过：取当前曲目兜底
            snap = ipc.snapshot()
            if (snap["title"] or snap["filename"]) and snap["connected"]:
                cover = ipc.cover_now(snap["cover_gen"])
                if cover is None:
                    cover = ipc.wait_cover(snap["cover_gen"], timeout=12.0)
                meta = {**{k: snap[k] for k in ("title", "artist", "album")}, "filename": snap.get("filename"), "duration_ms": snap.get("duration_ms"), "samplerate": snap.get("samplerate"), "file_size": snap.get("file_size"), "bit_rate": snap.get("bit_rate")}
                if cover is not None:
                    state["cover"], state["meta"], state["gen"] = cover, meta, snap["cover_gen"]
                    last_cover, last_meta, last_gen = cover, meta, snap["cover_gen"]
        if cover is not None or meta is not None:
            render(cover, meta, "热重载")
        else:
            applog.log("热重载：尚无曲目可渲染，跳过")

    # 日/夜主题跟随：每 ~3s 查一次系统主题，翻转后用当前曲目重渲染
    if cfg.get("theme_night_follow") and time.monotonic() - state["dark_t"] > 3.0:
        state["dark_t"] = time.monotonic()
        dark = wallpaper.system_is_dark()
        if state["dark"] is None:
            state["dark"] = dark
        elif dark != state["dark"] and (last_cover is not None or last_meta is not None):
            state["dark"] = dark
            render(last_cover, last_meta, "主题切换")

    # 暂停状态翻转：用当前曲目重渲染（pause_mode=off 时跳过）
    if cfg.get("pause_mode", "off") != "off":
        paused_now = ipc.snapshot().get("state") != 2  # 2=播放中，其余按暂停处理
        flipped = paused_now != state["paused"]
        state["paused"] = paused_now
        if flipped and (last_cover is not None or last_meta is not None):
            render(last_cover, last_meta, "暂停切换")

    gen = ipc.wait_track_change(timeout=0.5)
    if stop.is_set() or gen == last_gen or not ipc.snapshot()["connected"]:
        return
    snap = ipc.snapshot()
    if not snap["title"] and not snap["filename"]:
        return  # 元数据还没就绪，等下一轮
    meta_now = {**{k: snap[k] for k in ("title", "artist", "album")}, "filename": snap.get("filename"), "duration_ms": snap.get("duration_ms"), "samplerate": snap.get("samplerate"), "file_size": snap.get("file_size"), "bit_rate": snap.get("bit_rate")}

    # 同专辑连播：封面几乎必与上一首相同，先用上一张立即换壁纸，不等 AIMP 回图
    same_album = (last_cover is not None and last_meta is not None and meta_now["album"]
                  and meta_now["album"] == last_meta.get("album")
                  and meta_now["artist"] == last_meta.get("artist"))
    if same_album:
        t0 = time.monotonic()
        if render(last_cover, meta_now, "同专辑"):
            ms = (time.monotonic() - t0) * 1000
            applog.log(f"[切歌] 同专辑快速路径 耗时 {ms:.0f}ms（不等封面）")
            state["gen"], state["meta"] = gen, meta_now
            real = ipc.wait_cover(gen, timeout=6.0)  # 后台确认封面是否真的相同
            if real and real != last_cover and ipc.snapshot()["cover_gen"] == gen:
                applog.log("[切歌] 实际封面与上一首不同，补渲染")
                render(real, meta_now, "封面更新")
                state["cover"] = real
            return

    t_wait0 = time.monotonic()
    cover = ipc.wait_cover(gen, timeout=12.0)  # 覆盖 10s 封面重试窗口
    cover_ms = (time.monotonic() - t_wait0) * 1000
    if ipc.snapshot()["cover_gen"] != gen:
        return  # 等封面期间又切了歌：本轮作废，下一轮直接渲染最新曲目
    t_render0 = time.monotonic()
    if render(cover, snap, "切歌"):
        render_ms = (time.monotonic() - t_render0) * 1000
        applog.log(f"[切歌] 耗时: 封面 {cover_ms:.0f}ms + 渲染换图 {render_ms:.0f}ms "
                   f"= {cover_ms + render_ms:.0f}ms")
        state["gen"] = gen
        state["cover"], state["meta"] = cover, meta_now


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
    # 线程内的异常默认只打印到不可见的 stderr（--windowed 下等于消失），这里统一落盘
    threading.excepthook = lambda a: applog.log_exc(
        f"线程 {getattr(a.thread, 'name', '?')} 异常:\n", a.exc_type, a.exc_value, a.exc_traceback)
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

    lyrics = {"obj": None, "fetcher": None}

    def get_panel_pos():
        p = panel["obj"]
        if p is not None and not cfg.get("vis_hidden"):
            try:
                return p._screen_pos()
            except Exception:
                return None
        return None

    def on_lyrics_lines(lines):
        lw = lyrics["obj"]
        if lw is not None:
            lw.set_lines(lines)

    try:  # 歌词窗必须在频谱面板之后创建（seat_overlays 首登记者在最底）
        lyrics["obj"] = LyricsWindow(root, ipc, cfg, get_panel_pos)
        lyrics["fetcher"] = LyricsFetcher(ipc, cfg, on_lyrics_lines)
        lyrics["fetcher"].start()
    except Exception:
        applog.log_exc("歌词窗创建失败:\n", *sys.exc_info())

    # 面板配置监视：设置里改 面板宽度/高度/显示频谱面板 后 1s 内生效。
    # VisPanel 只在创建时读宽高，尺寸变化必须停采集线程后整体重建；
    # 可见状态下任何变化都重建（语义最稳），隐藏状态下只收起不重建。
    _panel_state = {"sig": None}

    def _watch_panel():
        try:
            w = int(cfg.get("vis_width", 420) or 420)
            h = int(cfg.get("vis_height", 120) or 120)
            hidden = bool(cfg.get("vis_hidden"))
            sig = (w, h, hidden)
            prev = _panel_state["sig"]
            if prev is None:
                _panel_state["sig"] = sig
                return
            if sig == prev:
                return
            _panel_state["sig"] = sig
            p = panel["obj"]
            if hidden:
                if p is not None:
                    p.win.withdraw()  # 不走 hide()：不回写 cfg
            else:
                if p is not None:
                    p.shutdown()
                    panel["obj"] = None
                show_vis()
        except Exception:
            applog.log_exc("面板配置监视异常:\n", *sys.exc_info())
        root.after(1000, _watch_panel)

    _panel_state["sig"] = (int(cfg.get("vis_width", 420) or 420),
                           int(cfg.get("vis_height", 120) or 120), bool(cfg.get("vis_hidden")))
    root.after(1000, _watch_panel)

    def toggle_lyrics():
        cfg["lyrics_hidden"] = not bool(cfg.get("lyrics_hidden"))
        config.save(cfg)  # 歌词窗 _tick 自管理显隐
        applog.log(f"歌词显隐切换: hidden={cfg['lyrics_hidden']}")

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
                on_toggle_lyrics=toggle_lyrics, on_restore=restore_wp, on_quit=_quit_app)
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
