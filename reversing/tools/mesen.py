#!/usr/bin/env python3
"""Mesen 无头驱动工具箱 —— 让 agent 独立观测/自动游玩,不再靠人当眼睛和手。

实测确认的能力(MesenCE 2.2.0, --testrunner)：
  · takeScreenshot() 返回 PNG 字符串 → print 十六进制 → 解码 → **能看到最终渲染画面**
    (含分屏 IRQ 之后的对话框，绕开"vblank 读不到分屏"那堵墙)。
  · getScreenBuffer() 返回 256×240 个 ARGB 整数 → 逐像素程序化分析(自建查看器)。
  · createSavestate()/loadSavestate(blob) —— **必须在主 CPU exec 内存回调里调用**
    (挂 NMI 入口 $E9C3，每帧一次)。blob 可 print 成 hex、跨进程重载 → **存档链突破 ~2 万帧上限**。
  · 也能直接 loadSavestate 现成的 .mss 文件内容(带 MSS 头，loadSavestate 照收)。
  · emu.read/write **必须带 memType**(emu.memType.nesMemory)，否则回调静默报错。
  · io/os/require = nil(沙箱禁)→ 一切经 print(stdout) 进出，不需要文件。

四个卡点的解法：
  1. 帧限(~2 万帧)  → 存档链(chain_savestate)。
  2. 有头无输出       → 不用有头，全程 testrunner + print/截图。
  3. 用不了查看器     → screenshot()=渲染画面(=Tilemap Viewer所见)；getScreenBuffer/read=原始数据自建查看器。
  4. 不能像人一样玩   → 截图(看)+ 读状态(判断)+ 存档(分支探索) = 视觉引导自动游玩 + 句子地图。
"""
import os
import re
import subprocess
import tempfile

MESEN = "/Applications/Mesen.app/Contents/MacOS/Mesen"
NMI = 0xE9C3  # MSG 的 NMI 入口(读 $FFFA 得)；exec 回调挂这里 → 每帧一次
SAVESTATE_DIR = os.path.expanduser("~/Library/Application Support/MesenCE/SaveStates")

# ---- Lua 片段库(拼进脚本) ----

PRELUDE = r"""
local M = emu.memType.nesMemory
local function rd(a) return emu.read(a, M) end
local function _hex(s) local t={} for i=1,#s do t[i]=string.format("%02x",s:byte(i)) end return table.concat(t) end
-- 打印一张截图(标记块，宿主 extract_pngs 解码)
local function shot(tag)
  local png = emu.takeScreenshot()
  print("SHOT_START "..(tag or "")); print(_hex(png)); print("SHOT_END")
end
-- 打印一个存档 blob(标记块，宿主 extract_blob 解码 → 下一段 loadSavestate)
local function dump_savestate(tag)
  local ss = emu.createSavestate()   -- 只能在 exec 回调里调
  print("BLOB_START "..(tag or "")); print(_hex(ss)); print("BLOB_END")
end
-- 把宿主给的 hex blob 解回字符串(用于 loadSavestate)
local function unhex(hex)
  local b={} for i=1,#hex,2 do b[#b+1]=string.char(tonumber(hex:sub(i,i+1),16)) end
  return table.concat(b)
end
"""


def run_lua(lua_code, rom, timeout=90, cwd=None):
    """在 testrunner 里跑 Lua，返回 stdout。lua_code 自动带 PRELUDE。
    ★stdout 走临时文件而非管道:实测 Mesen stdout 接 subprocess 管道会静默零输出/挂死
    (文件重定向/终端均正常,根因未明);文件重定向是可靠通路。"""
    full = PRELUDE + "\n" + lua_code
    with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as f:
        f.write(full)
        path = f.name
    outp = path + ".out"
    try:
        with open(outp, "w") as fo:
            subprocess.run([MESEN, "--testrunner", rom, path],
                           stdout=fo, stderr=subprocess.DEVNULL, timeout=timeout,
                           cwd=cwd or os.path.dirname(os.path.abspath(rom)))
        with open(outp, encoding="utf-8", errors="replace") as fi:
            return fi.read()
    finally:
        os.unlink(path)
        if os.path.exists(outp): os.unlink(outp)


def extract_pngs(stdout, outdir, prefix="shot"):
    """从 stdout 抓所有 SHOT_START <tag> / hex / SHOT_END 块，写成 png。返回 [(tag, path)]。"""
    os.makedirs(outdir, exist_ok=True)
    out = []
    lines = stdout.splitlines()
    i = 0
    n = 0
    while i < len(lines):
        m = re.match(r"SHOT_START ?(.*)", lines[i])
        if m and i + 1 < len(lines):
            tag = m.group(1).strip() or str(n)
            path = os.path.join(outdir, f"{prefix}_{tag}.png")
            with open(path, "wb") as f:
                f.write(bytes.fromhex(lines[i + 1].strip()))
            out.append((tag, path))
            n += 1
            i += 2
        i += 1
    return out


def extract_blob(stdout, tag=None):
    """抓 BLOB_START/hex/BLOB_END，返回 hex 字符串(直接嵌进下一段脚本用 unhex 还原)。"""
    lines = stdout.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"BLOB_START ?(.*)", ln)
        if m and (tag is None or m.group(1).strip() == tag):
            return lines[i + 1].strip()
    return None


def mss_hex(name):
    """读现成 .mss 存档文件的内容 → hex(loadSavestate 直接吃，含 MSS 头)。"""
    p = os.path.join(SAVESTATE_DIR, name)
    return open(p, "rb").read().hex()


def load_blob_lua(hexblob, at_frame=60):
    """生成"在第 at_frame 帧于 NMI 回调里 loadSavestate(该 blob)"的 Lua 前缀。"""
    return f"""
local _blobhex = "{hexblob}"
local _loaded = false
local _lf = 0
emu.addEventCallback(function() _lf = _lf + 1 end, emu.eventType.startFrame)
emu.addMemoryCallback(function()
  if not _loaded and _lf >= {at_frame} then
    _loaded = true
    emu.loadSavestate(unhex(_blobhex))
  end
end, emu.callbackType.exec, {NMI}, {NMI})
"""


if __name__ == "__main__":
    import sys
    # 演示：加载存档 → 跑几帧 → 截图。 用法: mesen.py <rom> <mss文件名> <输出png>
    rom, mss, outpng = sys.argv[1], sys.argv[2], sys.argv[3]
    lua = load_blob_lua(mss_hex(mss), at_frame=30) + """
local shot_done = false
emu.addEventCallback(function()
  if _loaded and not shot_done and _lf >= 90 then shot_done = true
    shot("main"); print("SCENE $0450="..rd(0x0450)); emu.stop(0)
  end
end, emu.eventType.startFrame)
"""
    sub = run_lua(lua, rom, timeout=60)
    pngs = extract_pngs(sub, os.path.dirname(outpng) or ".", prefix="demo")
    print(sub.split("SHOT_START")[0])  # 非截图输出
    for tag, p in pngs:
        os.replace(p, outpng)
        print("截图 ->", outpng)
