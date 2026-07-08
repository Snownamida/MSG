#!/usr/bin/env python3
"""完美遍历测绘器 · 累积通关探尽版(脚本流正解的合一体)。

判定实验证明本引擎是"脚本流":状态路径相关、同场景不同主线进度对话不同(回访态)。故完整遍历
= 主线累积推进(产生各进度场景入口) × 每场景内容去重探尽 × 全局句号汇总。本工具一趟通关做完:

- **累积、不回溯**地沿主线走 → 首次+回访态自然覆盖(单场景回溯爬会漏回访,已实证漏 15 句)
- 每到场景**探尽话题**:逐项选、看完、B 退回;全局按"句号是否见过"去重,不重复深挖已看内容
- **自动找前往**:探尽后逐项局部存档试探,选中导致场景($0450)变化的项 = 前往,选它推进
- 走到密语屏(场景00)= 第一章终点,停

输出全程句号→场景(reach.tsv)。可从任意场景 checkpoint 起跑;跨帧限用存档链(END blob 续跑)。
用法: explore.py <start.hex|none> <outdir> [start_step_hint]
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from mesen import run_lua, extract_blob, NMI

start = sys.argv[1]; outdir = sys.argv[2]
os.makedirs(outdir, exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROM = os.path.join(ROOT, "roms", "MSG-zh-demo.nes")
blob = "" if start == "none" else open(start).read().strip()

LUA = r'''
pcall(emu.setEmulationSpeed,0)
local PRG=emu.memType.nesPrgRom
local function prg(o) return emu.read(o,PRG) end
local frame=0
emu.addEventCallback(function() frame=frame+1 end, emu.eventType.startFrame)
local IDLE={a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}
local want=IDLE
emu.addEventCallback(function() pcall(emu.setInput,want,0) end, emu.eventType.inputPolled)
local function set(b) local t={} for k,v in pairs(IDLE) do t[k]=v end if b then t[b]=true end want=t end
-- 句号追踪(两表)
local seen={}
emu.addMemoryCallback(function()
  local p=rd(0x87)+rd(0x88)*256; local n
  if p>=0xBCB5 and p<0xBFFF and rd(0xA000)==prg(0) then n=(p-0xBCB5)//3
  elseif p>=0xA000 and p<0xBD4B and rd(0xA000)==prg(0x2000) then n=(p-0xA000)//3+281 end
  if n and not seen[n] then seen[n]=true; print(string.format("N\t%d\t%02X", n, rd(0x0450))) end
end, emu.callbackType.exec, 0xF071, 0xF071)

local co=coroutine.create(function()
  local function yf(n) for _=1,(n or 1) do coroutine.yield() end end
  local function tap(b,h,g) set(b); yf(h or 4); set(nil); yf(g or 12) end
  local function ready() return rd(0x17)==0x10 end
  local function to_menu(max)  -- 推进对话到就绪菜单态
    for _=1,(max or 80) do
      if ready() then return true end
      if rd(0x0200)==0xF0 then tap("a") else yf(5) end
    end
    return ready()
  end
  local function reset0() local t=0; while rd(0x2C)~=0 and t<14 do tap("up"); t=t+1 end end
  local function count()  -- 当前菜单项数
    to_menu(); reset0(); local mx=0
    for _=1,12 do tap("down"); if rd(0x2C)>mx then mx=rd(0x2C) else break end end
    reset0(); return mx+1
  end
  local function goto_cursor(i) reset0(); local t=0; while rd(0x2C)~=i and t<14 do tap("down"); t=t+1 end; return rd(0x2C)==i end
  -- ★递归探尽:穷尽当前菜单所有项(子菜单递归下探,对话看完,前往记下不选)。返回顶层前往项号(-1无)。
  -- DOWN-test 分类:选项后按 down,光标动=子菜单(递归)、不动=对话(推进看完);选后换场景=前往。
  local function exhaust(sc0, depth)
    local goto_i = -1
    reset0(); local cnt = count()
    for i=0,cnt-1 do
      if rd(0x0450)~=sc0 then break end
      reset0(); if not goto_cursor(i) then break end
      local snap = emu.createSavestate()
      tap("a",6,16); yf(8)
      if rd(0x0450)~=sc0 then                 -- 前往:回退,不推进(探尽阶段),记下
        emu.loadSavestate(snap); yf(6); if depth==0 then goto_i=i end
      else
        local c0=rd(0x2C)
        set("down"); yf(3); set(nil); yf(9)
        if rd(0x2C)~=c0 and depth<3 then      -- 光标动=子菜单 → 递归探尽
          reset0(); exhaust(sc0, depth+1)
          for _=1,4 do tap("b") end; to_menu(30)
        else                                  -- 对话 → 推进看完
          for _=1,50 do if ready() then break end if rd(0x0200)==0xF0 then tap("a") else yf(5) end end
          for _=1,4 do tap("b") end; to_menu(30)
        end
      end
    end
    return goto_i
  end

  if #"__BLOB__"==0 then while frame<3300 do yf() end; tap("start",4,40); to_menu(120) end
  yf(20)
  for guard=1,40 do
    local sc=rd(0x0450)
    if sc==0x00 then print("REACH_END 密语屏"); break end
    print(string.format("SCENE %02X @f%d", sc, frame))
    local g = exhaust(sc, 0)              -- 递归探尽整个场景
    if g<0 then                           -- 探尽后仍没顶层前往:再扫一遍找 goto
      reset0(); local cnt=count()
      for i=0,cnt-1 do
        reset0(); goto_cursor(i); local snap=emu.createSavestate(); tap("a",6,16); yf(8)
        if rd(0x0450)~=sc0 then g=i; emu.loadSavestate(snap); yf(6); break else emu.loadSavestate(snap); yf(6) end
      end
    end
    if g<0 then print("NO_ADVANCE 无前往,停 @"..string.format("%02X",sc)); break end
    print("ADVANCE via opt"..g)
    reset0(); goto_cursor(g); tap("a",6,16); to_menu(120)   -- 真推进
  end
end)
local loaded=false; local fin=false
emu.addMemoryCallback(function()
  if not loaded then if frame>=20 then if #"__BLOB__">0 then emu.loadSavestate(unhex("__BLOB__")) end; loaded=true end return end
  if coroutine.status(co)~="dead" then local ok,e=coroutine.resume(co); if not ok then print("ERR "..tostring(e)) end
  elseif not fin then fin=true
    print("DONE $0450="..string.format("%02X",rd(0x0450)))
    print("BLOB_START end"); print(_hex(emu.createSavestate())); print("BLOB_END"); emu.stop(0) end
  if frame>60000 then print("FRAMECAP"); print("BLOB_START end"); print(_hex(emu.createSavestate())); print("BLOB_END"); emu.stop(0) end
end, emu.callbackType.exec, __NMI__, __NMI__)
'''
LUA = LUA.replace("__BLOB__", blob).replace("__NMI__", str(NMI))
out = run_lua(LUA, ROM, timeout=int(os.environ.get("TO", "500")))
reach = []
with open(os.path.join(outdir, "reach.tsv"), "a") as f:
    for l in out.splitlines():
        if l.startswith("N\t"): f.write(l + "\n"); reach.append(l.split("\t"))
        elif l.startswith(("SCENE ", "ADVANCE", "REACH_END", "NO_ADVANCE", "DONE", "FRAMECAP", "ERR")): print(l)
b = extract_blob(out, "end")
if b: open(os.path.join(outdir, "explore_end.hex"), "w").write(b)
print(f"本段新增句号 {len(reach)} → reach.tsv")
