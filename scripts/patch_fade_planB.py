# -*- coding: utf-8 -*-
"""方案B：覆盖层内做交叉淡化 + 探测桌面真正刷新完成后再撤层。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\fade.py"
s = io.open(P, encoding="utf-8").read()

# ---------- 1. _Overlay 支持逐帧混合 ----------
if "def blend_to" not in s:
    s = s.replace("    def hide(self) -> None:",
'''    def load_rgb(self, img: Image.Image):
        """把一张图缓存成 RGB 数组（供逐帧混合）。"""
        im = img.convert("RGB")
        if im.size != (self.w, self.h):
            im = im.resize((self.w, self.h), Image.BILINEAR)
        return np.asarray(im, dtype=np.uint16)

    def blend_to(self, old_arr, new_arr, t: float) -> None:
        """把 old→new 按 t 混合后上屏（alpha=255，整块不透明）。"""
        t = max(0.0, min(1.0, t))
        if t <= 0.0:
            mix = old_arr
        elif t >= 1.0:
            mix = new_arr
        else:
            mix = (old_arr * (255 - int(255 * t)) + new_arr * int(255 * t)) // 255
        self.surface.arr[..., 0] = mix[..., 2]
        self.surface.arr[..., 1] = mix[..., 1]
        self.surface.arr[..., 2] = mix[..., 0]
        self.surface.arr[..., 3] = 255
        self.set_alpha(255)

    def hide(self) -> None:''')

# ---------- 2. 桌面层像素探测（不受覆盖层影响） ----------
if "def _desktop_pixel" not in s:
    s = s.replace("def _screen_pixel(x: int, y: int):",
'''def _desktop_pixel(x: int, y: int):
    """读"桌面窗口自身"的像素（不含我们的覆盖层），用于判断新壁纸是否已刷上。"""
    try:
        parent = desktop.find_desktop_parent()
        if not parent:
            return None
        hdc = desktop.user32.GetDC(parent)
        try:
            c = desktop.gdi32.GetPixel(hdc, int(x), int(y))
        finally:
            desktop.user32.ReleaseDC(parent, hdc)
        if c == 0xFFFFFFFF:
            return None
        return (c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF)
    except Exception:
        return None


def _screen_pixel(x: int, y: int):''')

# ---------- 3. 一个函数走完：铺旧图 → 交给调用方换图 → 交叉淡化 → 确认刷上 → 撤层 ----------
if "def transition(" not in s:
    s = s.rstrip() + '''


def transition_setup(old_layers):
    """用旧图快照铺满全屏（画面与当前完全一致）。失败返回 []。"""
    overlays = []
    try:
        for x, y, w, h, img in old_layers:
            ov = _Overlay(x, y, w, h, img)
            ov.set_alpha(255)
            overlays.append(ov)
        desktop.seat_overlays()
        _pump(30)
        return overlays
    except Exception:
        destroy_all(overlays)
        return []


def transition_finish(overlays, old_layers, new_layers, duration_ms: int = 220,
                      fps: int = 60) -> None:
    """交叉淡化到新图，并等到桌面真正换成新壁纸后再撤层（避免闪回）。"""
    if not overlays:
        return
    try:
        pairs = []
        for ov, old, new in zip(overlays, old_layers, new_layers):
            pairs.append((ov, ov.load_rgb(old[4]), ov.load_rgb(new[4])))

        steps = max(2, int(duration_ms / 1000.0 * fps))
        for i in range(1, steps + 1):
            t = i / steps
            for ov, old_arr, new_arr in pairs:
                ov.blend_to(old_arr, new_arr, t)
            _pump(1000.0 / fps)

        # 淡化结束，画面已经是新图；确认桌面确实刷上新图后再撤层，
        # 否则撤层瞬间会露出尚未刷新的旧壁纸（用户报的"闪回"）。
        probes = []
        for x, y, w, h, img in new_layers:
            a = np.asarray(img.convert("RGB"))
            for fx, fy in ((0.5, 0.35), (0.6, 0.6), (0.45, 0.75)):
                px, py = int(w * fx), int(h * fy)
                probes.append((x + px, y + py, tuple(int(v) for v in a[py, px])))

        end = time.perf_counter() + 1.0
        while time.perf_counter() < end:
            hit = 0
            checked = 0
            for sx, sy, want in probes:
                got = _desktop_pixel(sx, sy)
                if got is None:
                    continue
                checked += 1
                if all(abs(got[i] - want[i]) <= 26 for i in range(3)):
                    hit += 1
            if checked and hit >= max(1, checked * 2 // 3):
                break
            _pump(35)
    finally:
        destroy_all(overlays)
'''
io.open(P, "w", encoding="utf-8").write(s)
print("fade.py: 方案B 已就绪")
