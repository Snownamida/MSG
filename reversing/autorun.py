#!/usr/bin/env python3
"""用 scenetrace 验证过的"前进序列"headless 自动推进 + 句号追踪 + 存档checkpoint + 卡住截图。
思路(用户建议):不追求遍历所有分支,先用能持续前进的固定序列把主线推远,拿到主线句子顺序;
临近 testrunner ~2万帧上限时自动 createSavestate + 截图收尾,下次可从存档接着来。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesen import run_lua, extract_pngs, extract_blob, NMI

LUA = r"""
pcall(emu.setEmulationSpeed,0)
local M=emu.memType.nesMemory
local PRG=emu.memType.nesPrgRom
local function rd(a) return emu.read(a,M) end
local function prg(o) return emu.read(o,PRG) end
local function _hex(s) local t={} for i=1,#s do t[i]=string.format("%02x",s:byte(i)) end return table.concat(t) end

-- 输入(inputPolled里下发)
local IDLE={a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}
local KEY={A="a",B="b",up="up",down="down",left="left",right="right",start="start",select="select"}
local want=nil
emu.addEventCallback(function() pcall(emu.setInput, want or IDLE, 0) end, emu.eventType.inputPolled)
local function setbtn(name) local t={} for k,v in pairs(IDLE) do t[k]=v end if name then t[KEY[name] or name]=true end want=t end

-- 句号追踪
local lastN=-1
emu.addMemoryCallback(function()
  local p=rd(0x87)+rd(0x88)*256; local n
  if p>=0xBCB5 and p<0xBFFF and rd(0xA000)==prg(0) then n=(p-0xBCB5)//3
  elseif p>=0xA000 and p<0xBD4B and rd(0xA000)==prg(0x2000) then n=(p-0xA000)//3+281 end
  if n and n~=lastN then lastN=n; print(string.format("N\t%d\t%02X", n, rd(0x0450))) end
end, emu.callbackType.exec, 0xF071, 0xF071)

-- scenetrace 原语
local frame=0
local function fa() coroutine.yield() end
local function press(b) setbtn(b); fa(); fa(); setbtn(nil); fa(); fa() end
local stall=0
local function wait_ready(exit_if_cant)
  local timer=rd(0x9D); local w=0
  while rd(0x17)~=0x10 do fa(); w=w+1
    if exit_if_cant and rd(0x9D)==(timer-1)%256 then return false end
    if w>1200 then stall=stall+1; return false end end
  stall=0; return true
end
local function press_opt(b,times) for _=1,times do wait_ready(); press(b) end end
local function wait_page() local w=0
  while rd(0x0200)~=0xF0 do fa(); w=w+1; if w>1800 then return false end end; return true end
local function next_para(times)
  if type(times)=="number" then for _=1,times do if wait_page() then press("A") end end
  else while wait_ready(true)==false do if not wait_page() then break end; press("A") end end
end
local function option_view(opt,rep,dont_reset)
  for _=1,rep do local i=1
    while opt[i] do wait_ready(); local tries=0
      while rd(0x2C)~=opt[i]-1 do press_opt("down",1); wait_ready(); tries=tries+1; if tries>12 then break end end
      press_opt("A",1); i=i+1 end
    i=i-1; next_para("to_next_option")
    if not dont_reset then while opt[i] do wait_ready(); while rd(0x2C)~=0 do press_opt("up",1); wait_ready() end; press_opt("B",1); i=i-1 end end
  end
end

-- 前进序列(照搬 mesen_gui_scenetrace.lua,验证过能推到很远)
local co=coroutine.create(function()
  while frame<3300 do fa() end
  press("start"); for _=1,40 do fa() end
  next_para("to_next_option")
  option_view({1,1},2); option_view({1,2},2); option_view({2,1,1},1); option_view({2,2,1},2); option_view({3},1,true)
  option_view({1,1},2); option_view({1,2},2); option_view({2,1,1},2); option_view({2,2},2); option_view({3},2,true); option_view({3,1},1,true)
  option_view({1,1},2); option_view({1,2},3); option_view({2,1,1},4); option_view({2,1,2},2); option_view({3},1,true)
  option_view({3,3},1,true)
  option_view({1,1},2); option_view({1,2},1); option_view({2,1},1); option_view({2,1,1},2); option_view({2,1,2},1,true)
  press_opt("down",1); press_opt("A",1); next_para("to_next_option")
  option_view({1,1},1); option_view({2,1},1); option_view({2,2},1); option_view({1,2},1,true)
  press_opt("down",1); press_opt("A",1); next_para("to_next_option")
  press_opt("down",1); press_opt("A",1); next_para("to_next_option")
  press_opt("A",1); next_para("to_next_option")
  option_view({1,1},2); option_view({1,2},1); option_view({1,3},1); option_view({2,1},1); option_view({2,2},1)
  press_opt("down",3); press_opt("A",1); next_para(1)
  wait_ready(); press_opt("A",1); wait_ready()
  option_view({3},1,true)
  SEQ_DONE=true
end)

local REPORTED=false
local function report(why)
  if REPORTED then return end; REPORTED=true
  print("END "..why.." frame="..frame.." $0450="..string.format("%02X",rd(0x0450)))
  local png=emu.takeScreenshot()
  print("SHOT_START final"); print(_hex(png)); print("SHOT_END")
end
emu.addEventCallback(function()
  frame=frame+1
  if coroutine.status(co)~="dead" then pcall(coroutine.resume, co) end
end, emu.eventType.startFrame)
emu.addMemoryCallback(function()
  -- 存档/截图须在exec回调;临近帧限或序列跑完/卡死则收尾
  if not REPORTED and (SEQ_DONE or stall>=4 or frame>=18500) then
    local why = SEQ_DONE and "序列跑完" or (stall>=4 and "卡住stall" or "临近帧限")
    report(why)
    local ss=emu.createSavestate()
    print("BLOB_START end"); print(_hex(ss)); print("BLOB_END")
    emu.stop(0)
  end
end, emu.callbackType.exec, __NMI__, __NMI__)
"""


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    rom = os.path.join(os.path.dirname(here), "MSG-zh-demo.nes")
    lua = LUA.replace("__NMI__", str(NMI))
    out = run_lua(lua, rom, timeout=160)
    W = sys.argv[1] if len(sys.argv) > 1 else "."
    # 句号序列
    seq = [ln for ln in out.splitlines() if ln.startswith("N\t")]
    ends = [ln for ln in out.splitlines() if ln.startswith("END")]
    print("\n".join(ends))
    print(f"主线句号数(去重顺序): {len(seq)}")
    # 打印句号顺序(简洁)
    ns = [ln.split("\t")[1] for ln in seq]
    print("顺序:", " ".join(ns))
    # 截图 + 存档
    pngs = extract_pngs(out, W, prefix="auto")
    for tag, p in pngs:
        dst = os.path.join(W, "autorun_final.png"); os.replace(p, dst); print("SHOT ->", dst)
    blob = extract_blob(out, "end")
    if blob:
        open(os.path.join(W, "autorun_end.hex"), "w").write(blob)
        print("STATE_OUT ->", os.path.join(W, "autorun_end.hex"))


if __name__ == "__main__":
    main()
