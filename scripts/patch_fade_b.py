# -*- coding: utf-8 -*-
"""fade.py 增加：
1) crossfade_in_overlay(old_layer, new_layer, ms) —— 覆盖层内直接做旧→新交叉淡化
2) wait_painted(overlays, new_layers) —— 读 Progman 的 DC 探测桌面是否已换成新图
"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\fade.py"
s = io.open(P, encoding="utf-8").read()

if "def crossfade_in_overlay" in s:
    print("已存在")
    raise SystemExit

CODE = '''def _premult(arr_rgb, alpha=None):
    """PIL RGB → 预乘 BGRA（uint8，HxWx4）。"""
    a = np.asarray(arr_rgb.convert("RGB"))
    h, w = a.shape[:2]
    out = np.empty((h, w, 4), dtype=np.uint8)
    out[..., 0] = a[..., 2]
    out[..., 1] = a[..., 1]
    out[..., 2] = a[..., 0]
    out[..., 3] = 255
    return out


class _BlendOverlay(_Overlay):
    """在覆盖层内把 old 图逐帧混到 new 图。"""

    def __init__(self, x, y, w, h, old_img, new_img):
        self.old_pre = _premult(old_img.resize((w, h)) if old_img.size != (w, h) else old_img)
        self.new_pre = _premult(new_img.resize((w, h)) if new_img.size != (w, h) else new_img)
        # 用 old 图初始化窗口
        super().__init__(x, y, w, h, old_img, alpha_max=255)
        self._blend_buf = np.empty_like(self.old_pre, dtype=np.uint16)

    def blend_to(self, t: float) -> bool:
        """t=0 显示旧图，t=1 显示新图。"""
        if t >= 1.0:
            self.surface.arr[...] = self.new_pre
        elif t <= 0.0:
            self.surface.arr[...] = self.old_pre
        else:
            k_new = int(255 * t)
            k_old = 255 - k_new
            np.multiply(self.old_pre, k_old, out=self._blend_buf, dtype=np.uint16)
            self._blend_buf += self.new_pre * k_new
            np.right_shift(self._blend_buf, 8, out=self._blend_buf)
            self.surface.arr[...] = self._blend_buf.astype(np.uint8)
        return self.set_alpha(255)


def crossfade_in_overlay(old_layers, new_layers, duration_ms: int = 220, fps: int = 40):
    """覆盖层内直接做旧→新交叉淡化，返回覆盖层列表（结束时停在"新图"）。

    old_layers / new_layers: [(x, y, w, h, PIL.Image)]
    覆盖层出现时与当前桌面完全一致，随后画面在屏幕上平滑过渡到新壁纸，
    因此不需要"等系统刷屏"的空窗期——图标被遮挡时间 = 过渡时长。
    """
    overlays = []
    try:
        for (x, y, w, h, old_img), (_x, _y, _w, _h, new_img) in zip(old_layers, new_layers):
            overlays.append(_BlendOverlay(x, y, w, h, old_img, new_img))
        desktop.seat_overlays()
        _pump(20)
        steps = max(2, int(duration_ms / 1000.0 * fps))
        for i in range(1, steps + 1):
            t = i / steps
            for ov in overlays:
                ov.blend_to(t)
            _pump(1000.0 / fps)
        for ov in overlays:  # 收尾确保是完整新图
            ov.blend_to(1.0)
        return overlays
    except Exception:
        destroy_all(overlays)
        raise


def _progman_pixel(x: int, y: int):
    """读 Progman 的设备上下文像素（不含我们的覆盖层，用于探测壁纸是否真的刷上）。"""
    user32, gdi32 = desktop.user32, desktop.gdi32
    progman = user32.FindWindowW("Progman", None)
    if not progman:
        return None
    hdc = user32.GetDC(progman)
    if not hdc:
        return None
    try:
        c = gdi32.GetPixel(hdc, int(x), int(y))
        if c == 0xFFFFFFFF:
            return None
        return (c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF)
    finally:
        user32.ReleaseDC(progman, hdc)


def wait_painted(overlays, new_layers, timeout_ms: int = 1200) -> bool:
    """等桌面（Progman）真的显示新壁纸后再撤层，避免撤层瞬间闪回旧图。"""
    pts = []
    for x, y, w, h, img in new_layers:
        a = np.asarray(img.convert("RGB"))
        for fx, fy in ((0.30, 0.30), (0.55, 0.45), (0.75, 0.75)):
            px, py = int(w * fx), int(h * fy)
            pts.append((x + px, y + py, tuple(int(v) for v in a[py, px])))

    end = time.perf_counter() + timeout_ms / 1000.0
    while time.perf_counter() < end:
        hits = checked = 0
        for sx, sy, want in pts:
            got = _progman_pixel(sx, sy)
            if got is None:
                continue
            checked += 1
            if all(abs(got[i] - want[i]) <= 26 for i in range(3)):
                hits += 1
        if checked and hits >= max(1, checked * 2 // 3):
            return True
        _pump(40)
    return False


'''
s = s.replace("def destroy_all(overlays) -> None:", CODE + "def destroy_all(overlays) -> None:")
io.open(P, "w", encoding="utf-8").write(s)
print("fade.py: 已加 crossfade_in_overlay / wait_painted")
