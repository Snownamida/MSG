#!/usr/bin/env python3
"""探明命令菜单状态机:加载存档，逐帧记录 $2C/$17/$0200 变化，期间按 down/down/A，看清光标与就绪。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesen import run_lua, NMI

blob = open(sys.argv[1]).read().strip()

LUA = r"""
pcall(emu.setEmulationSpeed,0)
local M=emu.memType.nesMemory
local function rd(a) return emu.read(a,M) end
local function unhex(h) local b={} for i=1,#h,2 do b[#b+1]=string.char(tonumber(h:sub(i,i+1),16)) end return table.concat(b) end
local IDLE={a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}
local want=IDLE
emu.addEventCallback(function() pcall(emu.setInput,want,0) end, emu.eventType.inputPolled)
local START_HEX="__BLOB__"
local frame=0; local LOADED=false; local LA=0
local p2c,p17,p02=-999,-999,-999
local function set(b) local t={} for k,v in pairs(IDLE) do t[k]=v end if b then t[b]=true end want=t end
emu.addEventCallback(function()
  frame=frame+1
  if LOADED and frame>=LA+8 then
    local rf=frame-LA
    local c2,i7,i02=rd(0x2C),rd(0x17),rd(0x0200)
    if c2~=p2c or i7~=p17 or i02~=p02 then
      print(string.format("f%d $2C=%d $17=%02X $0200=%02X", rf, c2, i7, i02)); p2c,p17,p02=c2,i7,i02
    end
    if rf==40 then set("down") elseif rf==46 then set(nil)
    elseif rf==100 then set("down") elseif rf==106 then set(nil)
    elseif rf==160 then set("a") elseif rf==166 then set(nil)
    elseif rf>=260 then emu.stop(0) end
  end
end, emu.eventType.startFrame)
emu.addMemoryCallback(function()
  if not LOADED and frame>=20 then emu.loadSavestate(unhex(START_HEX)); LOADED=true; LA=frame end
end, emu.callbackType.exec, __NMI__, __NMI__)
"""

lua = LUA.replace("__BLOB__", blob).replace("__NMI__", str(NMI))
here = os.path.dirname(os.path.abspath(__file__))
rom = os.path.join(os.path.dirname(os.path.dirname(here)), "roms", "MSG-zh-demo.nes")
out = run_lua(lua, rom, timeout=45)
print(out)
