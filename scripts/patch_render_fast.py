# -*- coding: utf-8 -*-
"""渲染提速：背景改为 1/4 降采样（BOX 缩小最快）+ 封面阴影 1/3 尺寸算完再放大。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\wallpaper.py"
s = io.open(P, encoding="utf-8").read()

# ---------- 1. 背景：1/4 降采样 + BOX 下采样 ----------
OLD = '''        # 全是模糊，双线性足够；直接在 1/3 尺寸上等比铺满裁剪+模糊再放大（~10x 提速，视觉无差）
        sw, sh = max(2, w // 3), max(2, h // 3)
        im = cover.convert("RGB")
        scale = max(sw / im.width, sh / im.height)
        im = im.resize((max(sw, int(im.width * scale + 0.5)), max(sh, int(im.height * scale + 0.5))), Image.BILINEAR)
        x, y = (im.width - sw) // 2, (im.height - sh) // 2
        bg = im.crop((x, y, x + sw, y + sh))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=max(4, cfg["blur_radius"]) / 3.0))
        bg = bg.resize((w, h), Image.BILINEAR)'''
NEW = '''        # 背景本身就是模糊图：1/4 尺寸上算完再放大（BOX 缩小最快，视觉无差）
        sw, sh = max(2, w // 4), max(2, h // 4)
        im = cover.convert("RGB")
        scale = max(sw / im.width, sh / im.height)
        im = im.resize((max(sw, int(im.width * scale + 0.5)), max(sh, int(im.height * scale + 0.5))), Image.BOX)
        x, y = (im.width - sw) // 2, (im.height - sh) // 2
        bg = im.crop((x, y, x + sw, y + sh))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=max(4, cfg["blur_radius"]) / 4.0))
        bg = bg.resize((w, h), Image.BILINEAR)'''
if OLD in s:
    s = s.replace(OLD, NEW)
    print("背景：已改 1/4 + BOX")
else:
    print("背景段未匹配")

# ---------- 2. 封面投影：1/3 尺寸算完再放大 ----------
OLD2 = '''        shadow = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([40, 40, cw + 40, ch + 40], radius=max(6, min(cw, ch) // 60),
                                                 fill=(0, 0, 0, 130))
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))'''
NEW2 = '''        # 投影在小尺寸上生成再放大（高斯很贵，1/3 尺寸视觉等效）
        rad = max(6, min(cw, ch) // 60)
        k = 3
        sw2, sh2 = max(8, (cw + 80) // k), max(8, (ch + 80) // k)
        shadow = Image.new("RGBA", (sw2, sh2), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            [40 // k, 40 // k, (cw + 40) // k, (ch + 40) // k],
            radius=max(2, rad // k), fill=(0, 0, 0, 130))
        shadow = shadow.filter(ImageFilter.GaussianBlur(18 / k))
        shadow = shadow.resize((cw + 80, ch + 80), Image.BILINEAR)'''
if OLD2 in s:
    s = s.replace(OLD2, NEW2)
    print("封面投影：已改小尺寸+放大")
else:
    print("投影段未匹配")

io.open(P, "w", encoding="utf-8").write(s)
