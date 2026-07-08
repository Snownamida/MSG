#!/usr/bin/env python3
"""自动爬虫:探尽当前场景→找到并选「前往」→切场景→循环。存档分段续跑(绕2万帧限)。
输出:N(句号顺序) / SCENE(场景转移) / STEP(动作日志) / 结束存档blob + 截图。
从 --state 存档续跑(接着上次checkpoint);无则全新开机(需先跑到有菜单的场景)。

机制:$2C=菜单光标(0-based) $0450=场景 $0200==F0=对话翻页 $F071=句号点
      createSavestate/loadSavestate须在exec回调→用协程↔回调请求桥接(ss_req)。
"""
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
local function unhex(h) local b={} for i=1,#h,2 do b[#b+1]=string.char(tonumber(h:sub(i,i+1),16)) end return table.concat(b) end

local IDLE={a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}
local KEY={a="a",A="a",b="b",up="up",down="down",left="left",right="right",start="start",
  d="down",u="up",l="left",r="right"}
local want=nil
emu.addEventCallback(function() pcall(emu.setInput, want or IDLE, 0) end, emu.eventType.inputPolled)

-- 句号追踪 + 见过集合
local seen={}; local seen_n=0; local lastN=-1
emu.addMemoryCallback(function()
  local p=rd(0x87)+rd(0x88)*256; local n
  if p>=0xBCB5 and p<0xBFFF and rd(0xA000)==prg(0) then n=(p-0xBCB5)//3
  elseif p>=0xA000 and p<0xBD4B and rd(0xA000)==prg(0x2000) then n=(p-0xA000)//3+281 end
  if n and n~=lastN then lastN=n
    if not seen[n] then seen[n]=true; seen_n=seen_n+1 end
    print(string.format("N\t%d\t%02X", n, rd(0x0450)))
  end
end, emu.callbackType.exec, 0xF071, 0xF071)

-- 存/读档桥接(协程请求,exec回调执行)
local ss_req=0; local ss_blob=nil
-- 载入初始存档(如有)
local START_HEX="__STATEHEX__"
local LOADED = (#START_HEX==0)
local frame=0

local co  -- 前置声明
emu.addEventCallback(function()
  frame=frame+1
  if LOADED and co and coroutine.status(co)~="dead" then
    local ok,err=coroutine.resume(co)
    if not ok then print("CORO_ERR: "..tostring(err)) end
  end
end, emu.eventType.startFrame)

local REPORTED=false
emu.addMemoryCallback(function()
  if not LOADED then
    if frame>=20 then emu.loadSavestate(unhex(START_HEX)); LOADED=true end
    return
  end
  -- 存/读档请求
  if ss_req==1 then ss_blob=emu.createSavestate(); ss_req=0
  elseif ss_req==2 then emu.loadSavestate(ss_blob); ss_req=0 end
  -- 收尾
  if not REPORTED and (DONE or frame>=__MAXF__) then
    REPORTED=true
    print("END "..(DONE and tostring(DONE) or "帧限").." frame="..frame.." $0450="..string.format("%02X",rd(0x0450)).." seen="..seen_n)
    local png=emu.takeScreenshot(); print("SHOT_START final"); print(_hex(png)); print("SHOT_END")
    local ss=emu.createSavestate(); print("BLOB_START end"); print(_hex(ss)); print("BLOB_END")
    emu.stop(0)
  end
end, emu.callbackType.exec, __NMI__, __NMI__)

-- ===== 协程原语 =====
local function fa() coroutine.yield() end
local function yieldn(n) for _=1,(n or 1) do fa() end end
local function set(b) local t={} for k,v in pairs(IDLE) do t[k]=v end if b then t[KEY[b] or b]=true end want=t end
local function tap(b,hold,gap) set(b); yieldn(hold or 4); set(nil); yieldn(gap or 12) end
local function scene() return rd(0x0450) end
local function page_ready(to) local w=0 while rd(0x0200)~=0xF0 do fa(); w=w+1; if w>(to or 120) then return false end end return true end
local function adv(maxp) for _=1,(maxp or 50) do if not page_ready(90) then break end tap("a",4,12) end end
local function to_top() for _=1,14 do if rd(0x2C)==0 then break end tap("up",4,10) end end
local function count_opts() to_top(); local c=1
  for _=1,15 do tap("down",4,10); if rd(0x2C)==0 then break end c=c+1 end
  to_top(); return c end
local function cursor_to(t) local tr=0 while rd(0x2C)~=t and tr<20 do tap("down",4,10); tr=tr+1 end return rd(0x2C)==t end
local function back(n) for _=1,(n or 1) do tap("b",4,12) end end
local function do_save() ss_req=1; while ss_req~=0 do fa() end return ss_blob end
local function do_load(b) ss_blob=b; ss_req=2; while ss_req~=0 do fa() end yieldn(6) end
-- 场景变了:按B试图回到s0(看细节会回,真前往回不去)。返回是否回到了s0
local function try_return(s0) for _=1,5 do if scene()==s0 then return true end back(1); adv(4) end return scene()==s0 end

-- 探尽:把所有 look/talk 路径刷几轮,直到一轮无新句子或场景变了。返回 "TRAVELED"/"EXHAUSTED"
local function exhaust(max_rounds)
  for round=1,(max_rounds or 5) do
    local before=seen_n
    back(3); local n=count_opts()
    print("STEP exhaust round="..round.." 主菜单项数="..n)
    for opt=0,n-1 do
      back(3); to_top(); if not cursor_to(opt) then break end
      local s0=scene(); tap("a",4,16); adv(20)
      if scene()~=s0 and not try_return(s0) then print("STEP 探尽中opt"..opt.."真·切场景 "..string.format("%02X->%02X",s0,scene())); return "TRAVELED" end
      -- 可能进了子菜单:刷子菜单所有项(再下一层话题也刷)
      local m=count_opts()
      if m>=2 then
        for sub=0,m-1 do
          back(2); to_top(); cursor_to(opt); tap("a",4,14); adv(6)
          to_top(); cursor_to(sub); tap("a",4,14); adv(20)
          if scene()~=s0 and not try_return(s0) then return "TRAVELED" end
          local k=count_opts()
          if k>=2 then for tp=0,k-1 do
            back(1); to_top(); cursor_to(tp); tap("a",4,14); adv(20)
            if scene()~=s0 and not try_return(s0) then return "TRAVELED" end
          end end
          back(2)
        end
      end
    end
    print("STEP exhaust round="..round.." 新句="..(seen_n-before))
    if seen_n==before then return "EXHAUSTED" end
  end
  return "EXHAUSTED"
end

-- 找并选「前往」:存档,逐个顶层选项试选(+首个子项),看场景是否变;变了=前往,读档还原后正式选它
local function take_progress()
  back(3); local n=count_opts(); local s0=scene()
  local snap=do_save()
  for opt=0,n-1 do
    back(3); to_top(); cursor_to(opt); tap("a",4,16); adv(12)
    local moved = scene()~=s0
    if not moved then local m=count_opts(); if m>=1 then to_top(); cursor_to(0); tap("a",4,16); adv(12); moved=scene()~=s0 end end
    if moved then
      print("STEP 找到前往:顶层opt"..opt.." "..string.format("%02X->%02X",s0,scene()))
      return opt  -- 已经在新场景(试选即真选),不还原
    end
    do_load(snap)  -- 没动→还原,试下一个
  end
  return -1
end

-- ===== 主循环 =====
co=coroutine.create(function()
  yieldn(30)
  for iter=1,20 do
    local s=scene()
    print("STEP === 场景 "..string.format("%02X",s).." (iter"..iter..") 开始探尽 ===")
    local r=exhaust(5)
    if r=="TRAVELED" then
      print("STEP 探尽中已切场景")
    else
      print("STEP 场景"..string.format("%02X",s).."探尽完,找前往")
      local opt=take_progress()
      if opt<0 then print("STEP !! 找不到前往,卡关(需视觉介入) 场景"..string.format("%02X",s)); DONE="STALL"; return end
    end
    if frame>=(__MAXF__-500) then print("STEP 临近帧限,收尾存档"); DONE="FRAMELIMIT"; return end
  end
  DONE="DONE20iter"
end)
"""


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    rom = os.path.join(os.path.dirname(os.path.dirname(here)), "roms", "MSG-zh-demo.nes")
    W = sys.argv[1] if len(sys.argv) > 1 else "."
    state = sys.argv[2] if len(sys.argv) > 2 else None
    hexs = open(state).read().strip() if state and os.path.exists(state) else ""
    maxf = os.environ.get("CRAWL_MAXF", "17500")
    lua = LUA.replace("__NMI__", str(NMI)).replace("__STATEHEX__", hexs).replace("__MAXF__", maxf)
    out = run_lua(lua, rom, timeout=int(int(maxf) / 150) + 40)
    for ln in out.splitlines():
        if ln.startswith(("STEP", "END", "CORO_ERR", "SCENE")):
            print(ln)
    ns = [ln.split("\t")[1] for ln in out.splitlines() if ln.startswith("N\t")]
    print(f"句号数(去重前顺序 {len(ns)}):", " ".join(ns[-60:]))
    pngs = extract_pngs(out, W, prefix="crawl")
    for _, p in pngs:
        os.replace(p, os.path.join(W, "crawler_final.png")); print("SHOT ->", os.path.join(W, "crawler_final.png"))
    blob = extract_blob(out, "end")
    if blob:
        open(os.path.join(W, "crawler_end.hex"), "w").write(blob); print("STATE_OUT -> crawler_end.hex")


if __name__ == "__main__":
    main()
