#!/usr/bin/env python3
"""全章对话静态转储器 —— 动态抓各场景演出地址 × scandump 静态展开,汇总第一章对话目录。

白盒反编译闭环的落地(见 docs/SCRIPT_ENGINE.md):
  每场景动态选中顶层选项 → 抓 $EDE5 首次演出脚本地址 $1E/$20(演出入口,各场景不同)
  → scandump 静态展开该地址所在剧情段 → 汇总各场景各选项的对话。

对每个场景 checkpoint,遍历顶层若干命令(查看/交谈…)的首子项,抓演出地址、静态展开。
用法: chapterdump.py [scene_ckpt目录]   (默认用 qa6/scene_ckpt)
"""
import sys, os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "reversing", "tools"))
sys.path.insert(0, os.path.join(_ROOT, "reversing", "senmap"))
from mesen import run_lua, NMI
from scandump import segments
from scriptdis import sent

CKPT = sys.argv[1] if len(sys.argv) > 1 else \
    "/private/tmp/claude-503/-Users-jixiang-sun-Projects-tgv-max/172b0728-4e1b-440e-8ad9-683e2e0895a9/scratchpad/qa6/scene_ckpt"

# 抓一个场景、顶层命令 topcur、其子项 subcur 触发的演出脚本地址
_LUA = r'''
pcall(emu.setEmulationSpeed,0)
local frame=0
emu.addEventCallback(function() frame=frame+1 end, emu.eventType.startFrame)
local IDLE={a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}
local want=IDLE
emu.addEventCallback(function() pcall(emu.setInput,want,0) end, emu.eventType.inputPolled)
local function set(b) local t={} for k,v in pairs(IDLE) do t[k]=v end if b then t[b]=true end want=t end
local rec=false; local got=false
emu.addMemoryCallback(function(addr)
  if not rec or got then return end
  local p=rd(0x1E)+rd(0x1F)*256
  if p>=0xA000 and rd(0x20)>=0x80 and (rd(p)==0x4E or rd(p)==0x40) then got=true
    print(string.format("ADDR %04X %02X",p,rd(0x20))) end
end, emu.callbackType.exec, 0xEDE5, 0xEDE5)
local co=coroutine.create(function()
  local function yf(n) for _=1,(n or 1) do coroutine.yield() end end
  local function tap(b) set(b);yf(4);set(nil);yf(12) end
  local function pick(cur) local t=0; while rd(0x2C)~=0 and t<12 do tap("up");t=t+1 end
    t=0; while rd(0x2C)~=cur and t<8 do tap("down");t=t+1 end; tap("a") end
  yf(40)
  pick(__TOP__); yf(30)
  rec=true
  pick(__SUB__); yf(40)
end)
local loaded=false; local fin=false
emu.addMemoryCallback(function()
  if not loaded then if frame>=20 then emu.loadSavestate(unhex("__BLOB__")); loaded=true end return end
  if coroutine.status(co)~="dead" then coroutine.resume(co) elseif not fin then fin=true; emu.stop(0) end
  if frame>1400 then emu.stop(0) end
end, emu.callbackType.exec, __NMI__, __NMI__)
'''

def catch_addr(scene, top, sub):
    hexf = os.path.join(CKPT, f"scene_{scene}.hex")
    if not os.path.exists(hexf):
        return None
    blob = open(hexf).read().strip()
    lua = _LUA.replace("__BLOB__", blob).replace("__NMI__", str(NMI)) \
              .replace("__TOP__", str(top)).replace("__SUB__", str(sub))
    out = run_lua(lua, os.path.join(_ROOT, "roms", "MSG-zh-demo.nes"), timeout=90)
    for l in out.splitlines():
        if l.startswith("ADDR"):
            _, a, b = l.split()
            return int(b, 16), int(a, 16)
    return None


if __name__ == "__main__":
    # 场景 → 顶层命令数(查看=0/交谈=1);各取首子项
    scenes = ["0B", "0E", "12", "14", "11", "17"]
    print("=== 第一章对话静态转储(动态抓演出地址 × scandump 展开)===")
    for sc in scenes:
        for top, tname in [(0, "查看"), (1, "交谈")]:
            r = catch_addr(sc, top, 0)
            if not r:
                continue
            bank, addr = r
            segs = segments(bank, addr, 250)
            print(f"\n[场景{sc} {tname}→首项] 演出 bank{bank:02X}:${addr:04X}")
            for s, e, g in segs[:3]:
                print(f"   段 句{s}-{e}({len(g)}句): {sent(s)[:26]}")
