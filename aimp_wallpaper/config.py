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
    "bg_style": "blur",         # 背景方案 blur/blur_vignette/sharp/gradient
    "blur_radius": 28,          # 背景高斯模糊半径
    "darken": 0.75,             # 背景压暗系数 0~1
    "theme_night_follow": False,  # 跟随系统日/夜主题（深色主题叠黑色遮罩）
    "night_overlay": 30,        # 夜间黑色遮罩浓度（%）
    "cover_height_ratio": 0.56, # 无封面占位框占屏高比例
    "cover_margin_ratio": 0.12, # 封面左边距占屏高比例
    "cover_offset_x": 0,        # 封面 X 偏移(像素，可为负)
    "cover_offset_y": 0,        # 封面 Y 偏移(像素，可为负)
    "cover_scale": 1.0,         # 封面大小倍率 0.3~2.0
    # 每行样式（title=歌名 / artist=歌手 / album=专辑；sub_* 为旧版迁移源，仅作回退）
    "title_size_ratio": 0.075,  # 歌名字号占屏高比例
    "artist_size_ratio": 0.042, # 歌手字号占屏高比例
    "album_size_ratio": 0.042,  # 专辑字号占屏高比例
    "sub_size_ratio": 0.042,    # （旧版）副行字号，迁移源
    "title_font_file": None,    # 歌名字体文件（None=默认雅黑加粗）
    "artist_font_file": None,   # 歌手字体文件（None=跟随 sub_font_file→默认雅黑）
    "album_font_file": None,    # 专辑字体文件（None=跟随 sub_font_file→默认雅黑）
    "sub_font_file": None,      # （旧版）副行字体，迁移源
    "title_line_gap_ratio": 0.012,  # 歌名折行间距占屏高比例
    "title_sub_gap_ratio": 0.02,    # 歌名块与歌手行间距占屏高比例
    "sub_line_gap_ratio": 0.014,    # 歌手/专辑折行间距与行间占屏高比例
    "title_shadow": True,           # 歌名阴影
    "artist_shadow": True,          # 歌手阴影
    "album_shadow": True,           # 专辑阴影
    "text_shadow": True,            # （旧版）文字阴影，迁移源
    "title_stroke_w": 0,            # 歌名描边宽（像素，0=关）
    "artist_stroke_w": 0,           # 歌手描边宽
    "album_stroke_w": 0,            # 专辑描边宽
    "title_stroke_color": "#000000",    # 歌名描边色
    "artist_stroke_color": "#000000",   # 歌手描边色
    "album_stroke_color": "#000000",    # 专辑描边色
    "title_bold": True,             # 歌名加粗
    "artist_bold": False,           # 歌手加粗
    "album_bold": False,            # 专辑加粗
    "sub_bold": False,              # （旧版）副行加粗，迁移源
    "title_color": "#FFFFFF",       # 歌名颜色
    "artist_color": "#FFFFFF",      # 歌手颜色
    "album_color": "#FFFFFF",       # 专辑颜色
    "sub_color": "#FFFFFF",         # （旧版）副行颜色，迁移源
    "title_overflow": "wrap",       # 歌名过长：wrap=折行 / ellipsis=省略号
    "artist_overflow": "ellipsis",  # 歌手过长
    "album_overflow": "ellipsis",   # 专辑过长
    "sub_overflow": "ellipsis",     # （旧版）副行过长，迁移源
    "wrap_space_window": 5,     # 空格断行：折行点剩余部分前 N 字符内有空格则断在空格后（0=关）
    "show_text": True,
    "text_offset_x": 0,         # 文字区 X 偏移(像素)
    "text_offset_y": 0,         # 文字区 Y 偏移(像素)
    "text_align": "left",       # 文字水平对齐 left/center/right
    "text_valign": "center",    # 文字垂直对齐 top/center/bottom
    "restore_on_quit": True,    # 退出时恢复原壁纸（设置里可关）
    # 渲染产物目录（%LOCALAPPDATA%）
    "output_dir": os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "aimp-wallpaper"),
    # 可视化面板（AIMP 经典白条样式）
    "vis_width": 420,
    "vis_height": 120,
    "vis_pos": None,
    "vis_hidden": False,
    "vis_locked": False,        # 锁定频谱面板：仅禁拖动，仍跟随锚点
    "vis_fps": 30,              # 频谱刷新率（10~120）
    # 原壁纸（首次运行自动记录，restore 用）
    "original_wallpaper": None,
    "original_position": None,  # 原壁纸 fill 模式（DWPOS int）或 None
}

# 旧版 sub_*/text_shadow → 每行键的迁移映射（用户配置里已有新键时不动）
_MIGRATE_FROM_SUB = [
    ("artist_size_ratio", "sub_size_ratio"), ("album_size_ratio", "sub_size_ratio"),
    ("artist_font_file", "sub_font_file"), ("album_font_file", "sub_font_file"),
    ("artist_bold", "sub_bold"), ("album_bold", "sub_bold"),
    ("artist_color", "sub_color"), ("album_color", "sub_color"),
    ("artist_overflow", "sub_overflow"), ("album_overflow", "sub_overflow"),
]


def _migrate(cfg: dict, data: dict) -> None:
    if "artist_size_ratio" in data:
        return  # 已是新版配置
    for new, old in _MIGRATE_FROM_SUB:
        cfg[new] = cfg.get(old)
    for k in ("title_shadow", "artist_shadow", "album_shadow"):
        cfg[k] = bool(cfg.get("text_shadow", True))


def load() -> dict:
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
                _migrate(cfg, data)
        except (OSError, ValueError):
            pass
    return cfg


def save(cfg: dict) -> None:
    slim = {k: v for k, v in cfg.items() if k in DEFAULTS}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=2)
