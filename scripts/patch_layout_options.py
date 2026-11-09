# -*- coding: utf-8 -*-
"""新增布局参数：封面/文字的 XY 偏移、封面缩放、文字水平与垂直对齐。"""
import io

# ---------- 1. config 默认值 ----------
P = r"E:\aimp-wallpaper\aimp_wallpaper\config.py"
s = io.open(P, encoding="utf-8").read()
if "cover_offset_x" not in s:
    s = s.replace('    "cover_margin_ratio": 0.12, # 封面左边距占屏高比例',
                  '    "cover_margin_ratio": 0.12, # 封面左边距占屏高比例\n'
                  '    "cover_offset_x": 0,        # 封面 X 偏移(像素，可为负)\n'
                  '    "cover_offset_y": 0,        # 封面 Y 偏移(像素，可为负)\n'
                  '    "cover_scale": 1.0,         # 封面大小倍率 0.3~2.0')
    s = s.replace('    "show_text": True,',
                  '    "show_text": True,\n'
                  '    "text_offset_x": 0,         # 文字区 X 偏移(像素)\n'
                  '    "text_offset_y": 0,         # 文字区 Y 偏移(像素)\n'
                  '    "text_align": "left",       # 文字水平对齐 left/center/right\n'
                  '    "text_valign": "center",    # 文字垂直对齐 top/center/bottom')
    io.open(P, "w", encoding="utf-8").write(s)
    print("config.py: 已加 7 个布局键")
else:
    print("config.py: 已有，跳过")

# ---------- 2. wallpaper 渲染 ----------
P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()

# 2a) 封面缩放 + 偏移
OLD = """        max_h = int(h * 0.82)
        max_w = int(w * 0.52)
        scale = min(1.0, max_h / ih, max_w / iw)
        if scale < 1.0:
            cover = cover.resize((max(1, int(iw * scale)), max(1, int(ih * scale))), Image.LANCZOS)
        cw, ch = cover.size
        cy = (h - ch) // 2"""
NEW = """        max_h = int(h * 0.82)
        max_w = int(w * 0.52)
        fit = min(1.0, max_h / ih, max_w / iw)
        user_scale = max(0.3, min(2.0, float(cfg.get("cover_scale", 1.0) or 1.0)))
        scale = fit * user_scale
        if abs(scale - 1.0) > 1e-3:
            cover = cover.resize((max(1, int(iw * scale)), max(1, int(ih * scale))), Image.LANCZOS)
        cw, ch = cover.size
        cy = (h - ch) // 2 + int(cfg.get("cover_offset_y", 0) or 0)"""
if OLD in s:
    s = s.replace(OLD, NEW)
    print("wallpaper: 封面缩放/偏移已加")
else:
    print("wallpaper: 封面段未匹配!")

# 2b) 占位框也跟随 Y 偏移
s = s.replace("""        ch = int(h * cfg["cover_height_ratio"])
        cw = ch
        cy = (h - ch) // 2""",
              """        ch = int(int(h * cfg["cover_height_ratio"]) *
                 max(0.3, min(2.0, float(cfg.get("cover_scale", 1.0) or 1.0))))
        cw = ch
        cy = (h - ch) // 2 + int(cfg.get("cover_offset_y", 0) or 0)""")

# 2c) 封面 cx 加偏移（cx 定义在更早）
s = s.replace('    cx = int(h * cfg["cover_margin_ratio"])',
              '    cx = int(h * cfg["cover_margin_ratio"]) + int(cfg.get("cover_offset_x", 0) or 0)')

# 2d) 文字区偏移 + 对齐 + 垂直对齐
OLD_T = """            line_gap = int(h * cfg.get("title_line_gap_ratio", 0.012))
            sub_gap = int(h * cfg.get("sub_line_gap_ratio", 0.014))
            block_gap = int(h * cfg.get("title_sub_gap_ratio", 0.02))
            th = title_font.size * len(lines) + line_gap * (len(lines) - 1)
            sh = sub_font.size * len(sub_lines) + sub_gap * (len(sub_lines) - 1)
            ty = cy + (ch - (th + block_gap + sh)) // 2"""
NEW_T = """            line_gap = int(h * cfg.get("title_line_gap_ratio", 0.012))
            sub_gap = int(h * cfg.get("sub_line_gap_ratio", 0.014))
            block_gap = int(h * cfg.get("title_sub_gap_ratio", 0.02))
            th = title_font.size * len(lines) + line_gap * (len(lines) - 1)
            sh = sub_font.size * len(sub_lines) + sub_gap * (len(sub_lines) - 1)
            block_h = th + block_gap + sh
            dy = int(cfg.get("text_offset_y", 0) or 0)
            valign = cfg.get("text_valign", "center")
            if valign == "top":
                ty = cy + dy
            elif valign == "bottom":
                ty = cy + ch - block_h + dy
            else:
                ty = cy + (ch - block_h) // 2 + dy
            align = cfg.get("text_align", "left")
            if align == "center":
                draw_x, draw_anchor = tx + tw_max // 2, "ma"
            elif align == "right":
                draw_x, draw_anchor = tx + tw_max, "ra"
            else:
                draw_x, draw_anchor = tx, "la\""""
NEW_T = NEW_T.replace('"la\\"', '"la"')
if OLD_T in s:
    s = s.replace(OLD_T, NEW_T)
    print("wallpaper: 文字偏移/对齐已加")
else:
    print("wallpaper: 文字段未匹配!")

# 2e) 绘制改用 draw_x / draw_anchor
s = s.replace("""                _draw_shadow_text(layer, (tx, ty), ln, title_font, fill=(tr, tg, tb, 255),
                                  stroke_width=title_stroke, shadow=shadow)""",
              """                _draw_shadow_text(layer, (draw_x, ty), ln, title_font, fill=(tr, tg, tb, 255),
                                  stroke_width=title_stroke, shadow=shadow, anchor=draw_anchor)""")
s = s.replace("""                _draw_shadow_text(layer, (tx, ty), s, sub_font, fill=(sr, sg, sb, 255),
                                  stroke_width=sub_stroke, shadow=shadow)""",
              """                _draw_shadow_text(layer, (draw_x, ty), s, sub_font, fill=(sr, sg, sb, 255),
                                  stroke_width=sub_stroke, shadow=shadow, anchor=draw_anchor)""")

# 2f) 文字区起始 x 加偏移
s = s.replace('        tx = cx + cw + int(h * 0.055)',
              '        tx = cx + cw + int(h * 0.055) + int(cfg.get("text_offset_x", 0) or 0)')

io.open(P, "w", encoding="utf-8").write(s)
print("wallpaper.py 写入完成")
