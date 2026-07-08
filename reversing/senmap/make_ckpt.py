#!/usr/bin/env python3
"""开机→NEW GAME→推进开场到第一个命令菜单→存档(当前 build 的干净基准)。
用法: make_ckpt.py <rom> <out.hex>"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "reversing", "tools"))
from mesen import run_lua, extract_blob, extract_pngs, NMI

rom = sys.argv[1]; out = sys.argv[2]
SP = os.environ.get("SP", tempfile.gettempdir())

LUA = f'''
pcall(emu.setEmulationSpeed,0)
local PRG=emu.memType.nesPrgRom
local function prg(o) return emu.read(o,PRG) end
local IDLE={{a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}}
local want=IDLE
emu.addEventCallback(function() pcall(emu.setInput,want,0) end, emu.eventType.inputPolled)
local function set(b) local t={{}} for k,v in pairs(IDLE) do t[k]=v end if b then t[b]=true end want=t end
local frame=0
emu.addEventCallback(function() frame=frame+1 end, emu.eventType.startFrame)
local co=coroutine.create(function()
  local function yf(n) for _=1,(n or 1) do coroutine.yield() end end
  local function tap(b,h,g) set(b); yf(h or 4); set(nil); yf(g or 14) end
  local function wait_ready(exit) local t=rd(0x9D); local w=0
    while rd(0x17)~=0x10 do yf(); w=w+1; if exit and rd(0x9D)==(t-1)%256 then return false end if w>1200 then return false end end return true end
  local function wait_page(to) local w=0 while rd(0x0200)~=0xF0 do yf(); w=w+1; if w>(to or 1800) then return false end end return true end
  while frame<3300 do yf() end
  tap("start",4,40)
  -- 推进开场对话到第一个命令菜单(wait_ready 成功=菜单)
  for _=1,200 do
    if wait_ready(true) then break end
    if not wait_page(600) then break end
    tap("a",4,10)
  end
  yf(30)
  print("CKPT $0450="..string.format("%02X",rd(0x0450)).." $2C="..rd(0x2C).." $0200="..string.format("%02X",rd(0x0200)).." frame="..frame)
end)
local reported=false
emu.addEventCallback(function()
  if coroutine.status(co)~="dead" then local ok,e=coroutine.resume(co); if not ok then print("ERR "..tostring(e)) end end
end, emu.eventType.startFrame)
emu.addMemoryCallback(function()
  if coroutine.status(co)=="dead" and not reported then reported=true
    shot("ckpt"); print("BLOB_START end"); print(_hex(emu.createSavestate())); print("BLOB_END"); emu.stop(0) end
end, emu.callbackType.exec, {NMI}, {NMI})
'''
o = run_lua(LUA, rom, timeout=120)
for ln in o.splitlines():
    if ln.startswith(("CKPT", "ERR")): print(ln)
b = extract_blob(o, "end")
if b: open(out, "w").write(b); print("saved", out, len(b)//2, "bytes")
extract_pngs(o, SP, prefix="ckpt")
