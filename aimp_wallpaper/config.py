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
    "blur_type": "gauss",       # 模糊类型 gauss/soft/fog/glow（高斯系四变体，blur 类方案下生效）
    "blur_radius": 28,          # 背景模糊半径（各模糊类型共用的强度基准）
    "darken": 0.75,             # 背景压暗系数 0~1
    "fade_native": True,       # 换壁纸过渡：用 Windows 原生淡入（幻灯片引擎武装）
    "theme_night_follow": False,  # 跟随系统日/夜主题（深色主题叠黑色遮罩）
    "night_overlay": 30,        # 夜间黑色遮罩浓度（%）
    "cover_height_ratio": 0.56, # 无封面占位框占屏高比例（内部几何，不暴露）
    "cover_margin_ratio": 0.12, # 封面左边距占屏高比例（GUI 可调）
    "cover_offset_x": 0,        # 封面 X 偏移(像素，可为负)
    "cover_offset_y": 0,        # 封面 Y 偏移(像素，可为负)
    "cover_scale": 1.0,         # 封面大小倍率 0.3~2.0
    "cover_anchor": "left",     # 封面基准边 left=左缘固定（向右伸展）/ right=右缘固定（向左伸展，文字位置恒定）
    "cover_radius": 0,          # 封面圆角半径（0=自动=短边/60）
    "cover_shadow_alpha": 130,  # 封面阴影浓度（0=无阴影）
    "cover_shadow_offset": 40,  # 封面阴影外扩偏移(像素)
    "cover_stroke_w": 0,        # 封面描边宽（0=关）
    "cover_stroke_color": "#000000",  # 封面描边色
    # 暂停状态显示
    "pause_mode": "darken",     # off=不处理 / darken=压暗 / badge=角标 / both
    "pause_darken": 30,         # 暂停压暗浓度（%）
    "pause_darken_scope": "all",  # 压暗范围 all=整幅 / bg=仅背景
    "pause_shrink": False,      # 暂停时封面缩小（可选效果）
    "pause_shrink_pct": 8,      # 封面缩小幅度（%）
    # 每行样式（title=歌名 / artist=歌手 / album=专辑 / info=歌曲信息；sub_* 为旧版迁移源）
    "title_show": True,         # 是否显示歌名
    "artist_show": True,        # 是否显示歌手
    "album_show": True,         # 是否显示专辑
    "info_show": True,          # 是否显示歌曲信息行
    "line_order": ["title", "artist", "album", "info"],  # 右侧四行的显示顺序（设置页可上移/下移）
    "info_template": "{format} {samplerate} {bitrate} {bits}",  # 歌曲信息模板
    #   可用 token：{format} {samplerate} {bitrate} {bits} {duration}
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
    "info_size_ratio": 0.042,   # 歌曲信息字号占屏高比例（迁移时从专辑行播种）
    "info_font_file": None,     # 歌曲信息字体文件（None=默认雅黑）
    "info_shadow": True,        # 歌曲信息阴影
    "info_stroke_w": 0,         # 歌曲信息描边宽
    "info_stroke_color": "#000000",  # 歌曲信息描边色
    "info_bold": False,         # 歌曲信息加粗
    "info_color": "#FFFFFF",    # 歌曲信息颜色
    "title_bold": True,             # 歌名加粗
    "artist_bold": False,           # 歌手加粗
    "album_bold": False,            # 专辑加粗
    "sub_bold": False,              # （旧版）副行加粗，迁移源
    "title_color": "#FFFFFF",       # 歌名颜色
    "artist_color": "#FFFFFF",      # 歌手颜色
    "album_color": "#FFFFFF",       # 专辑颜色
    "sub_color": "#FFFFFF",         # （旧版）副行颜色，迁移源
    "title_overflow": "wrap",       # 歌名过长：wrap=折行（最多 4 行，无省略号）/ ellipsis=单行省略号
    "artist_overflow": "ellipsis",  # 歌手过长（同上）
    "album_overflow": "ellipsis",   # 专辑过长（同上）
    "info_overflow": "ellipsis",    # 歌曲信息过长（同上）
    "sub_overflow": "ellipsis",     # （旧版）副行过长，迁移源
    "wrap_space_window": 5,     # （旧版）全局空格断行，迁移源
    "title_space_window": 5,    # 歌名空格断行窗口（折行点剩余部分前 N 字符内有空格则断在空格后，0=关）
    "artist_space_window": 5,   # 歌手空格断行窗口
    "album_space_window": 5,    # 专辑空格断行窗口
    "info_space_window": 0,     # 歌曲信息空格断行窗口（信息行短，默认关）
    # 歌词悬浮窗（样式与壁纸歌名行同源，迁移时从 title_* 播种）
    "lyrics_hidden": False,     # True=隐藏歌词窗
    "lyrics_follow": "panel",   # 跟随目标 panel=频谱面板 / anchor=壁纸文字区 / fixed=屏幕右下固定
    "lyrics_show_next": True,   # 显示下一行原文
    "lyrics_show_trans": True,  # 显示当前行译文（仅当前行模式下关掉=严格单行）
    "lyrics_lang_pref": "zh-Hans",  # 多语言歌词优先：zh-Hans 简体 / zh-Hant 繁体 / any 取第一个
    "lyrics_width": 420,        # 歌词窗宽度（px，实时生效）
    "lyrics_locked": False,     # 锁定=禁拖动（仍跟随锚点）
    "lyrics_pos": None,         # 手动定位 [x, y]（拖过后粘滞）
    "lyrics_font_file": None,   # 歌词字体（None=默认雅黑加粗）
    "lyrics_size_ratio": 0.032, # 当前歌词行字号占屏高比例
    "lyrics_color": "#FFFFFF",  # 当前歌词行颜色
    "lyrics_next_color": "#B0B0B0",  # 下一行颜色
    "lyrics_stroke_w": 2,       # 歌词描边宽（0=关）
    "lyrics_stroke_color": "#000000",  # 歌词描边色
    "lyrics_shadow": True,      # 歌词阴影
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
    "vis_fmax": 16000,          # 频谱最高频率（Hz）：此前是幽灵键，不在 DEFAULTS 永不持久化
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
    if data.get("blur_type") not in (None, "gauss", "soft", "fog", "glow"):
        cfg["blur_type"] = "gauss"  # v0.2.4 的六种非高斯类型已删，旧值回落标准高斯
    # 歌词样式与壁纸歌名行保持一致（首次升级时播种，之后各自独立）
    for lyr, title in (("lyrics_font_file", "title_font_file"), ("lyrics_color", "title_color"),
                       ("lyrics_shadow", "title_shadow")):
        if lyr not in data:
            cfg[lyr] = cfg.get(title)
    # 歌曲信息行样式从专辑行播种（首次升级时，之后各自独立）
    for info_k, alb_k in (("info_size_ratio", "album_size_ratio"),
                          ("info_font_file", "album_font_file"), ("info_bold", "album_bold"),
                          ("info_color", "album_color"), ("info_overflow", "album_overflow"),
                          ("info_shadow", "album_shadow"), ("info_stroke_w", "album_stroke_w"),
                          ("info_stroke_color", "album_stroke_color")):
        if info_k not in data:
            cfg[info_k] = cfg.get(alb_k)
    for new, old in _MIGRATE_FROM_SUB:
        if new not in data:
            cfg[new] = cfg.get(old)
    # v0.2.4 及更早：全局 wrap_space_window → 每行 space_window
    for g in ("title", "artist", "album"):
        if f"{g}_space_window" not in data:
            cfg[f"{g}_space_window"] = cfg.get("wrap_space_window",
                                               DEFAULTS["wrap_space_window"])
    if "artist_size_ratio" not in data:  # 旧版格式才从 text_shadow 播种三行阴影
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
    # 原子写：直接覆写 CONFIG_PATH 时进程被杀/断电会留下半截 JSON，
    # 下次启动 load() 解析失败 → 全部设置静默回默认
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)
