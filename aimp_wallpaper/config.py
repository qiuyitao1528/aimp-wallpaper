"""config.json 读写：默认值 + 落盘。"""
import json
import os
import shutil
import sys


def _resolve_config_path() -> str:
    """开发态=项目根；打包后 exe 旁有 portable.flag=便携（配置在 exe 旁），否则安装版（%LOCALAPPDATA%）。"""
    if not getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
    exe_dir = os.path.dirname(sys.executable)
    if os.path.exists(os.path.join(exe_dir, "portable.flag")):
        return os.path.join(exe_dir, "config.json")
    cfg_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "aimp-wallpaper")
    os.makedirs(cfg_dir, exist_ok=True)
    dst = os.path.join(cfg_dir, "config.json")
    src = os.path.join(exe_dir, "config.json")
    if not os.path.exists(dst) and os.path.exists(src):  # 绿色版原地装新版：迁移一次旧配置
        try:
            shutil.copyfile(src, dst)
        except OSError:
            pass
    return dst


CONFIG_PATH = _resolve_config_path()

DEFAULTS = {
    # 壁纸
    "blur_radius": 28,          # 背景高斯模糊半径
    "darken": 0.75,             # 背景压暗系数 0~1
    "cover_height_ratio": 0.56, # 无封面占位框占屏高比例
    "cover_margin_ratio": 0.12, # 封面左边距占屏高比例
    "title_size_ratio": 0.075,  # 歌名字号占屏高比例
    "sub_size_ratio": 0.042,    # 歌手/专辑字号占屏高比例
    "title_font_file": None,    # 歌名字体文件（None=默认雅黑加粗）
    "sub_font_file": None,      # 副行字体文件（None=默认雅黑常规）
    "title_line_gap_ratio": 0.012,  # 歌名折行间距占屏高比例
    "title_sub_gap_ratio": 0.02,    # 歌名块与副行间距占屏高比例
    "sub_line_gap_ratio": 0.014,    # 副行行间距占屏高比例
    "text_shadow": True,            # 文字阴影（歌名+副行）
    "title_bold": True,             # 歌名加粗
    "sub_bold": False,              # 副行加粗
    "title_color": "#FFFFFF",       # 歌名颜色
    "sub_color": "#FFFFFF",         # 副行颜色
    "title_overflow": "wrap",       # 歌名过长：wrap=折行 / ellipsis=省略号
    "sub_overflow": "ellipsis",     # 副行过长：ellipsis=省略号 / wrap=折行（每条最多 2 行）
    "show_text": True,
    "restore_on_quit": True,    # 退出时恢复原壁纸（设置里可关）
    # 渲染产物目录（%LOCALAPPDATA%）
    "output_dir": os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "aimp-wallpaper"),
    # 小部件
    "widget_alpha": 235,        # 0~255
    "widget_width": 460,
    "widget_pos": None,         # [x, y] 屏幕坐标；None=底部居中
    # 可视化面板（AIMP 经典白条样式）
    "vis_width": 420,
    "vis_height": 120,
    "vis_pos": None,
    "vis_hidden": False,
    "vis_locked": False,        # 锁定频谱面板：仅禁拖动，仍跟随锚点
    "vis_fps": 30,              # 频谱刷新率（10~120）
    "lyrics_hidden": False,     # 隐藏歌词（显示在频谱面板下方）
    "lyrics_locked": False,     # 锁定歌词：仅禁拖动，仍跟随
    "lyrics_pos": None,         # 歌词手动位置
    "widget_hidden": False,     # 隐藏桌面音乐控件
    "bg_style": "blur",         # 背景方案：blur=高斯模糊 / blur_vignette=模糊+暗角 / sharp=原图铺满 / gradient=主色渐变
    # 原壁纸（首次运行自动记录，restore 用）
    "original_wallpaper": None,
    "original_position": None,  # 原壁纸 fill 模式（DWPOS int）或 None
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
        except (OSError, ValueError):
            pass
    return cfg


def save(cfg: dict) -> None:
    slim = {k: v for k, v in cfg.items() if k in DEFAULTS}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=2)
