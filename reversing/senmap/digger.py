#!/usr/bin/env python3
"""挖掘机:从场景检查点穷尽话题分支(嵌套 i.j × 多轮,停滞即止),记录可达句号 + 每句页截图。

与 crawl.py(状态签名 DFS,系统但慢)互补:digger 是话题网格穷尽(i∈0-4 主菜单项 × j∈0-2
子菜单项 × 5 轮),快、直接覆盖"反复深挖"能滚出的深句。产出 dig_<tag>.tsv(句号→场景,纯数字)
供 audit.py 汇总判"完美"。用法: digger.py <scene_ckpt.hex> <outdir> <tag>
"""
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "reversing", "tools"))
from mesen import run_lua, extract_pngs, NMI

ck, outdir, tag = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(outdir, exist_ok=True)
ROM = os.path.join(ROOT, "roms", "MSG-zh-demo.nes")
blob = open(ck).read().strip()

LUA = r'''
pcall(emu.setEmulationSpeed,0)
local PRG=emu.memType.nesPrgRom
local function prg(o) return emu.read(o,PRG) end
local frame=0
emu.addEventCallback(function() frame=frame+1 end, emu.eventType.startFrame)
local IDLE={a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}
local want=nil
emu.addEventCallback(function() pcall(emu.setInput,want or IDLE,0) end, emu.eventType.inputPolled)
local function setbtn(n) local t={} for k,v in pairs(IDLE) do t[k]=v end if n then t[n]=true end want=t end
local lastN=-1; local lastNf=0; local seen={}; local lastNew=0
emu.addMemoryCallback(function()
  local p=rd(0x87)+rd(0x88)*256; local n
  if p>=0xBCB5 and p<0xBFFF and rd(0xA000)==prg(0) then n=(p-0xBCB5)//3
  elseif p>=0xA000 and p<0xBD4B and rd(0xA000)==prg(0x2000) then n=(p-0xA000)//3+281 end
  if n and n~=lastN then lastN=n; lastNf=frame
    if not seen[n] then seen[n]=true; lastNew=frame; print(string.format("N\t%d\t%02X", n, rd(0x0450))) end
  end
end, emu.callbackType.exec, 0xF071, 0xF071)
local shotd={}
emu.addMemoryCallback(function()
  if lastN>=0 and (frame-lastNf)>=12 and not shotd[lastN] and rd(0x17)~=0x10 then
    shotd[lastN]=true
    local png=emu.takeScreenshot()
    print("SHOT_START d"..lastN.."_"..string.format("%02X",rd(0x0450))); print(_hex(png)); print("SHOT_END")
  end
end, emu.callbackType.exec, __NMI__, __NMI__)
local co=coroutine.create(function()
  local function fa(n) for _=1,(n or 1) do coroutine.yield() end end
  local function press(b) setbtn(b); fa(3); setbtn(nil); fa(10) end
  local function wait_ready(x)
    local t=rd(0x9D); local w=0
    while rd(0x17)~=0x10 do fa(); w=w+1
      if x and rd(0x9D)==(t-1)%256 then return false end
      if w>900 then return false end end
    return true end
  local function next_para()
    while wait_ready(true)==false do
      local w=0; while rd(0x0200)~=0xF0 and rd(0x17)~=0x10 do fa(); w=w+1; if w>900 then break end end
      if rd(0x17)==0x10 then break end
      press("a") end
  end
  local function cursor_to(i)
    wait_ready(); local tries=0
    while rd(0x2C)~=i and tries<14 do press("down"); wait_ready(); tries=tries+1 end
    return rd(0x2C)==i
  end
  for r=1,5 do
    for i=0,4 do
      for j=0,2 do
        if not cursor_to(i) then break end
        press("a"); wait_ready()
        if rd(0x17)==0x10 and rd(0x2C)==0 then
          if cursor_to(j) then press("a") end
        end
        next_para()
        wait_ready(); press("b"); wait_ready()
        if frame-lastNew>3500 and r>2 then print("EXHAUSTED r="..r); return end
        if frame>15500 then print("FRAMECAP"); return end
      end
    end
  end
end)
local loaded=false; local fin=false
emu.addMemoryCallback(function()
  if not loaded then if frame>=20 then emu.loadSavestate(unhex("__BLOB__")); loaded=true end return end
  if coroutine.status(co)~="dead" then local ok,e=coroutine.resume(co); if not ok then print("ERR "..tostring(e)) end
  elseif not fin then fin=true; print("DIG_DONE frames="..frame); emu.stop(0) end
end, emu.callbackType.exec, __NMI__, __NMI__)
'''
LUA = LUA.replace("__BLOB__", blob).replace("__NMI__", str(NMI))
out = run_lua(LUA, ROM, timeout=300)
ns = []
with open(os.path.join(outdir, f"dig_{tag}.tsv"), "w") as f:
    for l in out.splitlines():
        if l.startswith("N\t"): f.write(l + "\n"); ns.append(l.split("\t")[1])
        elif l.startswith(("DIG_DONE", "EXHAUSTED", "FRAMECAP", "ERR")): print(" ", l)
pngs = extract_pngs(out, os.path.join(outdir, "pages"), prefix=f"g{tag}")
deep = [n for n in ns if int(n) > 216]
print(f"[{tag}] 句号 {len(ns)}(深句 {len(deep)}: {','.join(deep[:15])}{'…' if len(deep)>15 else ''}) 截图 {len(pngs)}")
