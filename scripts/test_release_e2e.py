# -*- coding: utf-8 -*-
"""端到端：从 GitHub Release 下载 zip → 解压空目录 → 隔离环境启动 → 验渲染。

证明"别人下载到的产物"本身可用（不是只有本地能跑）。
"""
import glob
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile

ZIP_URL = "https://github.com/qiuyitao1528/aimp-wallpaper/releases/download/v0.1.2/aimp-wallpaper-v0.1.2-win64.zip"
TMP = os.path.join(tempfile.gettempdir(), "aimp-e2e")
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)
zip_path = os.path.join(TMP, "dl.zip")

print("下载 zip ...")
urllib.request.urlretrieve(ZIP_URL, zip_path)
print("  大小:", round(os.path.getsize(zip_path) / 1048576, 1), "MB")

app = os.path.join(TMP, "app")
os.makedirs(app)
with zipfile.ZipFile(zip_path) as z:
    names = z.namelist()
    print("  条目数:", len(names), "| 含 exe:", any(n.endswith(".exe") for n in names))
    z.extractall(app)
exe = os.path.join(app, "aimp-wallpaper.exe")
print("  解压出 exe:", os.path.exists(exe))

LA = os.path.join(TMP, "la")
os.makedirs(LA, exist_ok=True)
env = dict(os.environ)
env["LOCALAPPDATA"] = LA
if os.path.exists(os.path.join(app, "portable.flag")):
    os.remove(os.path.join(app, "portable.flag"))

proc = subprocess.Popen([exe], cwd=app, env=env)
print("启动 PID:", proc.pid)
time.sleep(18)

out = os.path.join(LA, "aimp-wallpaper")
cfg_p = os.path.join(out, "config.json")
log_p = os.path.join(out, "aimp-wallpaper.log")
ok = True
print("config:", "OK" if os.path.exists(cfg_p) else "FAIL")
ok &= os.path.exists(cfg_p)
if os.path.exists(log_p):
    txt = open(log_p, encoding="utf-8", errors="replace").read()
    hit = [ln for ln in txt.splitlines() if "已更新" in ln or "渲染路径" in ln]
    print("日志关键行:", hit[:3] if hit else "无渲染记录")
    ok &= any("已更新" in ln for ln in txt.splitlines())
else:
    print("日志 FAIL")
    ok = False
pngs = glob.glob(os.path.join(out, "wallpaper_*.png"))
print("壁纸产物:", [os.path.basename(p) for p in pngs] or "FAIL")
ok &= bool(pngs)
alive = proc.poll() is None
print("进程存活:", alive)
ok &= alive
proc.kill()
time.sleep(1)
print("=== 端到端结论:", "线上产物可用" if ok else "线上产物有问题", "===")
