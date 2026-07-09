#!/usr/bin/env python3
"""主线推进器 —— 双轨遍历架构的「动态轨」。

背景(第二章踩坑得来的方法论):第一章几乎全是对话菜单场景,老的探尽爬虫够用;但推广到全游戏,
主线要穿过 **CG 过场**(如穿梭机发射,$0200=FF)、**密语/存档屏**(场景00)等特殊场景。对这些
场景绝不能按选项(一按 option 就把状态搞卡死)。本推进器按**场景类型分类分流**,并用**存档链**
纯等把 CG 播完(绕过 testrunner ~2万帧限)。它只负责「把主线推进到各场景 + 沿途存干净 checkpoint」;
提对话交给「白盒轨」(scandump/autoscript 从 checkpoint 静态提取),绕开动态遍历在特殊场景的卡点。

场景分类分流(每帧):
  · 场景00(密语/CONTINUE屏)     → 选「还是再叫醒一次」(cursor0)推进下一章;记为章边界
  · $0200==F0(对话翻页)          → 按 A
  · $17==0x10(菜单就绪)          → 探尽记句号 + 选末项(通常「前往」)推进
  · 其余($0200==FF 等 CG/特殊)   → 纯等(偶尔 A 防卡),CG 靠存档链续播到切场景

用法:
  runner.py <workdir> [start.hex] [start_scene_hint]
  环境: RUN_MAXF(每段帧数,默认16000)  SAVE_SCENES=1(存每场景入口checkpoint)
输出: N(句号→场景) / SCENE(转移) / SCENECKPT(场景存档) / END(段尾存档,供续跑)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesen import run_lua, extract_blob, extract_pngs, NMI

LUA = r"""
pcall(emu.setEmulationSpeed,0)
local PRG=emu.memType.nesPrgRom
local function prg(o) return emu.read(o,PRG) end
local function _hex(s) local t={} for i=1,#s do t[i]=string.format("%02x",s:byte(i)) end return table.concat(t) end
local function unhex(h) local b={} for i=1,#h,2 do b[#b+1]=string.char(tonumber(h:sub(i,i+1),16)) end return table.concat(b) end

local IDLE={a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}
local KEY={A="a",B="b",up="up",down="down",left="left",right="right",start="start",select="select"}
local want=IDLE
emu.addEventCallback(function() pcall(emu.setInput, want or IDLE, 0) end, emu.eventType.inputPolled)
local function set(b) local t={} for k,v in pairs(IDLE) do t[k]=v end if b then t[KEY[b] or b]=true end want=t end

local frame=0
local lastN=-1; local lastScene=-1; local lastNframe=0
local SAVESCENES=(__SAVESCENES__==1); local scene_saved={}
emu.addEventCallback(function() frame=frame+1 end, emu.eventType.startFrame)

-- 句号追踪(两表:主 $BCB5 / 深句 $A000 bank1)
emu.addMemoryCallback(function()
  local p=rd(0x87)+rd(0x88)*256; local n
  if p>=0xBCB5 and p<0xBFFF and rd(0xA000)==prg(0) then n=(p-0xBCB5)//3
  elseif p>=0xA000 and p<0xBD4B and rd(0xA000)==prg(0x2000) then n=(p-0xA000)//3+281 end
  if n and n~=lastN then lastN=n; lastNframe=frame; print(string.format("N\t%d\t%02X",n,rd(0x0450))) end
end, emu.callbackType.exec, 0xF071, 0xF071)

local START_HEX="__START_HEX__"
local LOADED=(#START_HEX==0)
local CAP=__CAP__
local DONE=false; local REPORTED=false

local co=coroutine.create(function()
  local function yf(n) for _=1,(n or 1) do coroutine.yield() end end
  local function tap(b) set(b);yf(4);set(nil);yf(12) end
  local function reset0() local t=0; while rd(0x2C)~=0 and t<12 do tap("up");t=t+1 end end
  -- 从开机则先过标题 NEW GAME
  if #START_HEX==0 then
    while frame<3300 do yf() end
    tap("start"); yf(40)
  end
  local kk=0; local stuck_sc=-1; local stuck_n=-1; local stuck_f=0
  while frame<CAP do
    kk=kk+1
    local sc=rd(0x0450); local p2=rd(0x0200); local rdy=rd(0x17)
    if sc==0x00 then                              -- 密语/CONTINUE屏(章边界):选「还是再叫醒一次」(cursor0)推进
      print("CHBORDER f"..frame.." 密语屏")
      reset0(); tap("a"); yf(20)
    elseif p2==0xF0 then                           -- 对话翻页
      tap("a")
    elseif rdy==0x10 then                          -- 菜单就绪:探尽(触发句号)+ 选末项前往
      reset0()
      local mx=0; for _=1,8 do tap("down"); if rd(0x2C)>mx then mx=rd(0x2C) else break end end
      reset0(); local t=0; while rd(0x2C)~=mx and t<10 do tap("down");t=t+1 end
      tap("a")
    else                                           -- $0200==FF(对话演出/纯CG/交互):混合推进
      -- CG 需按键+方向推进(穿梭机等);对话演出按A即进;交互场景久推不动→由卡点检测记为 SCENESTUCK
      local m=kk%6
      if m==0 or m==2 then set("a") elseif m==1 then set("down") elseif m==3 then set("right")
      elseif m==4 then set("up") else set(nil) end
      yf(9)
    end
    -- 卡点检测:场景+句号长期无进展 = 交互卡点(动态过不了)→ 存档交白盒补,结束本段
    if sc~=stuck_sc or lastN~=stuck_n then stuck_sc=sc; stuck_n=lastN; stuck_f=frame
    elseif frame-stuck_f>2200 then
      print("SCENESTUCK "..string.format("%02X",sc).." f"..frame.." ".._hex(emu.createSavestate()))
      DONE=true; return
    end
  end
  DONE=true
end)

emu.addEventCallback(function()
  if LOADED and co and coroutine.status(co)~="dead" then
    if lastScene~=rd(0x0450) then lastScene=rd(0x0450); print("SCENE "..string.format("%02X",lastScene).." @f"..frame) end
    local ok,err=coroutine.resume(co); if not ok then print("CORO_ERR "..tostring(err)) end
  end
end, emu.eventType.startFrame)

emu.addMemoryCallback(function()
  if not LOADED then if frame>=20 then emu.loadSavestate(unhex(START_HEX)); LOADED=true end return end
  -- 每场景入口 checkpoint(菜单就绪态)
  if SAVESCENES then local sc=rd(0x0450)
    if not scene_saved[sc] and rd(0x0200)~=0xF0 and rd(0x17)==0x10 then
      scene_saved[sc]=true; print("SCENECKPT "..string.format("%02X",sc).." ".._hex(emu.createSavestate()))
    end
  end
  if not REPORTED and (DONE or frame>=CAP+2000) then
    REPORTED=true
    print("END frame="..frame.." $0450="..string.format("%02X",rd(0x0450)).." "..(DONE and "序列态" or "帧限"))
    local png=emu.takeScreenshot(); print("SHOT_START final"); print(_hex(png)); print("SHOT_END")
    print("BLOB_START end"); print(_hex(emu.createSavestate())); print("BLOB_END")
    emu.stop(0)
  end
end, emu.callbackType.exec, __NMI__, __NMI__)
"""


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    rom = os.path.join(os.path.dirname(os.path.dirname(here)), "roms", "MSG-zh-demo.nes")
    W = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(W, exist_ok=True)
    state = sys.argv[2] if len(sys.argv) > 2 else None
    hexs = open(state).read().strip() if state and os.path.exists(state) else ""
    cap = os.environ.get("RUN_MAXF", "16000")
    savescenes = "1" if os.environ.get("SAVE_SCENES") else "0"
    lua = (LUA.replace("__NMI__", str(NMI)).replace("__START_HEX__", hexs)
           .replace("__CAP__", cap).replace("__SAVESCENES__", savescenes))
    out = run_lua(lua, rom, timeout=int(int(cap) / 120) + 60)
    ck = os.path.join(W, "scene_ckpt"); os.makedirs(ck, exist_ok=True)
    for ln in out.splitlines():
        if ln.startswith("SCENECKPT "):
            p = ln.split(" ", 2); fn = os.path.join(ck, f"scene_{p[1]}.hex")
            if not os.path.exists(fn):
                open(fn, "w").write(p[2]); print("SCENECKPT ->", fn)
        if ln.startswith("SCENESTUCK "):
            p = ln.split(" ", 3); fn = os.path.join(ck, f"stuck_{p[1]}.hex")
            open(fn, "w").write(p[3]); print("SCENESTUCK ->", fn, "(交互卡点,交白盒补对话)")
    for ln in out.splitlines():
        if ln.startswith(("SCENE ", "END", "CHBORDER", "CORO_ERR")):
            print(ln)
    ns = [ln for ln in out.splitlines() if ln.startswith("N\t")]
    with open(os.path.join(W, "scene_map.tsv"), "a") as f:
        for ln in ns:
            f.write(ln + "\n")
    print(f"本段句号采样 {len(ns)} 行 → scene_map.tsv")
    extract_pngs(out, W, prefix="run")
    b = extract_blob(out, "end")
    if b:
        open(os.path.join(W, "runner_end.hex"), "w").write(b); print("STATE_OUT -> runner_end.hex")


if __name__ == "__main__":
    main()
