# AIMP Wallpaper

桌面壁纸跟随 [AIMP](https://www.aimp.ru/) 当前播放歌曲实时变化：专辑封面海报式壁纸（封面 1:1 清晰居左、右侧歌名/歌手/专辑、背景为封面高斯模糊），附带 AIMP 经典样式频谱面板与系统托盘。

![screenshot](docs/screenshot.png)

## 功能

- **海报式动态壁纸**：随播放自动更新；封面原尺寸不放大、超屏才等比缩小；多显示器逐屏渲染
- **频谱面板**：AIMP 经典样式（白条 + 点状峰值帽），WASAPI 环回自算 FFT（4096 点、线性频率轴，与 AIMP 官方实现一致），可拖动/锁定/隐藏
- **系统托盘**：设置、显示/隐藏频谱面板、恢复原壁纸、退出
- **丰富的壁纸排版设置**（设置窗口分「壁纸 / 文字 / 排版 / 面板 / 系统」五页）：
  - 壁纸：背景模糊半径、封面大小倍率（0.5~1.6）、封面 X/Y 偏移
  - 文字：歌名与副行各自的字号、字体（枚举系统全部字体）、颜色、加粗、过长处理（换行/省略号）；文字阴影
  - 排版：标题-副行间距、标题行间距、副行行间距、文字 X/Y 偏移、文字水平对齐（左/中/右）、垂直对齐（顶/中/底）
- **渲染**：UpdateLayeredWindow 逐像素 alpha 原子呈现，无闪烁；刷新率 10~120fps 可调
- **其他**：配置热重载（保存立即生效）、单实例、首次运行自动记录原壁纸（`restore` 子命令或卸载时自动恢复）、运行日志

## 安装

从 [Releases](../../releases) 下载：

- `aimp-wallpaper-vX.Y.Z-setup.exe`：安装版（per-user 免管理员，含开始菜单/自启/卸载）
- `aimp-wallpaper-vX.Y.Z-win64.zip`：绿色版，解压即用（配置生成在 exe 旁）

系统要求：Windows 10 / 11，[AIMP](https://www.aimp.ru/)（v5.40 实测，需其 Remote API）。

## 使用

- 托盘图标右键：设置 / 显示-隐藏频谱面板 / 恢复原壁纸 / 退出
- 频谱面板右键：拖动定位、锁定（禁拖动，仍跟随壁纸锚点）、隐藏、退出
- 退出默认恢复原壁纸（设置里可关）；`aimp-wallpaper.exe restore` 可手动恢复

## 从源码运行 / 构建

```bash
# 运行（uv 管理，Python 3.12+）
uv run python -m aimp_wallpaper          # 启动
uv run python -m aimp_wallpaper restore  # 恢复原壁纸

# 打包 exe（PyInstaller）
uv run pyinstaller --noconfirm --clean --windowed --name aimp-wallpaper \
  --icon assets/icon.ico --add-data "assets/icon.png;." \
  --collect-all pyaudiowpatch --collect-all pystray run.py

# 安装包（Inno Setup 6+）
iscc installer.iss
```

## 原理

- **数据源**：AIMP 自带 Remote API（`AIMP2_RemoteInfo` 窗口消息 + 共享内存 + WM_COPYDATA 封面推送），零插件依赖。常量已按 AIMP v5.40.2727 实测校准（`scripts/probe_aimp.py`）
- **封面**：`GET_ALBUMART(29)` → AIMP 回推 WM_COPYDATA（dwData=`0x41495043`，图片字节流）。切歌后 10s 重试窗口内重试（切歌瞬间 AIMP 可能还没解析好封面）
- **元数据**：共享内存 2048 字节，`0x00`=字符串区偏移(0x58)、`0x28` 起依次 Album/Artist/Date/FileName/Genre/Title 字符长度，`0x58` 起紧凑 UTF-16
- **频谱**：AIMP 官方可视化即线性频率轴直出 FFT bin（见 `apiVisuals.h`），本面板对齐该实现；采集走 WASAPI 环回（pyaudiowpatch），帧间做时间线性插值
- **渲染**：PIL 海报式渲染，PNG 输出；模糊背景 1/3 尺寸降采样加速；封面/背景按内容哈希缓存
- **覆盖窗口**：Win11 26300 上 `SetParent` 进 Progman/WorkerW 的窗口不被 DWM 合成，改用**顶层窗口 + `UpdateLayeredWindow` 逐像素 alpha 原子呈现 + `SetWindowPos` 把 Progman 压到窗口下方**（Rainmeter/Lively 同思路）
- **设壁纸**：comtypes 手写 `IDesktopWallpaper`（IID `B92B56A9-8B55-4E14-9A89-0199BBB6F93B`——网上常见 IID 有误），逐屏 SetWallpaper

## 已知限制

- 在线电台曲目可能无封面 → 显示深色占位图（正常行为）
- AIMP 未运行时壁纸保持不变，IPC 每 5s 重连
- 静默安装（/VERYSILENT）时若壁纸正在运行需先关闭（GUI 安装会自动提示）

## License

[MIT](LICENSE)
