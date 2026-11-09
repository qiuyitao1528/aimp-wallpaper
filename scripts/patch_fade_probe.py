# -*- coding: utf-8 -*-
"""用 1 像素透明探针孔探测桌面是否已换图（Progman DC 读不到像素时的解决办法）。"""
import io

P = r"E:\aimp-wallpaper\aimp_wallpaper\fade.py"
s = io.open(P, encoding="utf-8").read()

# 1) _BlendOverlay：计算探针像素（新旧图差异最大处），present 时挖空该像素
s = s.replace('''        self._buf = np.empty_like(self.old_pre, dtype=np.uint16)
        self.surface.arr[...] = self.old_pre''',
'''        self._buf = np.empty_like(self.old_pre, dtype=np.uint16)
        # 探针点：新旧图颜色差异最大的像素（用于透过 1px 小孔判断桌面是否已刷新）
        diff = np.abs(self.old_pre[..., :3].astype(np.int16) - self.new_pre[..., :3].astype(np.int16))
        flat = diff.sum(axis=2)
        py, px = np.unravel_index(int(np.argmax(flat)), flat.shape)
        self.probe = (int(px), int(py))
        self.probe_new = tuple(int(v) for v in self.new_pre[py, px, 2::-1])  # RGB
        self.probe_old = tuple(int(v) for v in self.old_pre[py, px, 2::-1])
        self.surface.arr[...] = self.old_pre''')

s = s.replace('''    def present(self) -> None:
        user32 = desktop.user32''',
'''    def present(self) -> None:
        px, py = self.probe
        self.surface.arr[py, px, :] = 0  # 挖 1 像素透明孔，用来探测桌面真实像素
        user32 = desktop.user32''')

# 2) wait_painted 改成读屏幕上的探针孔
s = s.replace('''def _progman_pixel(x: int, y: int):
    """读 Progman 的 DC（不含覆盖层），用于判断壁纸是否真的刷上。"""
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
        user32.ReleaseDC(progman, hdc)''',
'''def _probe_pixel(x: int, y: int):
    """读屏幕上的一个像素（覆盖层在该点挖了 1px 透明孔，读到的就是真实桌面）。"""
    from PIL import ImageGrab
    try:
        return ImageGrab.grab(bbox=(int(x), int(y), int(x) + 1, int(y) + 1)).convert("RGB").getpixel((0, 0))
    except Exception:
        return None''')

s = s.replace('''def wait_painted(new_layers, timeout_ms: int = 1200) -> bool:
    """等桌面真的显示新壁纸（撤层前确认，避免闪回旧图）。"""
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
    return False''',
'''def wait_painted(overlays, timeout_ms: int = 1000) -> bool:
    """透过覆盖层的 1px 探针孔，等桌面真正显示新壁纸再返回（避免撤层闪回旧图）。"""
    if not overlays:
        return False
    end = time.perf_counter() + timeout_ms / 1000.0
    while time.perf_counter() < end:
        ok = 0
        for ov in overlays:
            px, py = ov.probe
            got = _probe_pixel(ov.pos[0] + px, ov.pos[1] + py)
            if got is None:
                continue
            if all(abs(got[i] - ov.probe_new[i]) <= 26 for i in range(3)):
                ok += 1
        if ok == len(overlays):
            return True
        _pump(35)
    return False''')

io.open(P, "w", encoding="utf-8").write(s)
print("已加 1px 探针孔探测")
