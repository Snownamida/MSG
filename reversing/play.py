#!/usr/bin/env python3
"""交互式游玩驱动器 —— agent 的"手+眼+记忆"。

一步 = 从某存档出发、执行一串按键、跑到稳定、然后报告:
  · 截图 PNG(我用来"看")
  · 关键状态($0450场景 / $2C菜单光标 / $17就绪 / $0200翻页箭头 / 当前句号)
  · 本段经过的句号序列 SEQ(测绘句子地图用)
  · 结束时的存档 blob(写文件，下一步 --state 接着这里跑 → 存档链，不受 2 万帧限)

按键 DSL(空格分隔，可 name*N 重复)：
  start  a(等就绪后按A,推进对话/确认菜单)  A(强制按A不等待)
  d/u/l/r(方向)  b(取消)  wN(等N帧)  shot(中途多拍一张)

用法:
  python3 reversing/play.py --state none      --actions "w200" --out s0.hex --shot t.png   # 全新开机
  python3 reversing/play.py --state s0.hex     --actions "start w60 a a a" --out s1.hex --shot t.png
  python3 reversing/play.py --state MSG-zh-demo_11.mss --actions "a a" ...   # .mss文件名=读现成存档
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesen import run_lua, extract_pngs, extract_blob, mss_hex, NMI

ROM = os.environ.get("ROM", "MSG-zh-demo.nes")


def build_lua(start_state_hex, actions, trail=40):
    """生成执行脚本。start_state_hex=None 则全新开机。"""
    acts_lua = "{" + ",".join(f'"{a}"' for a in actions) + "}"
    load_block = ""
    if start_state_hex:
        load_block = f'''
  -- 先读档(exec回调内)，读完才开始动作
  if not LOADED then
    if frame >= 20 then emu.loadSavestate(unhex(START_HEX)); LOADED = true; LOADED_AT = frame end
    return
  end
  if frame < LOADED_AT + 8 then return end   -- 读档后缓冲几帧
'''
    else:
        load_block = "  if not LOADED then LOADED = true end\n"

    return f'''
pcall(emu.setEmulationSpeed, 0)
local PRG = emu.memType.nesPrgRom
local function prg(o) return emu.read(o, PRG) end
local START_HEX = "{start_state_hex or ""}"
local ACTIONS = {acts_lua}
local IDLE = {{a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false}}
local KEY = {{a="a",A="a",b="b",d="down",u="up",l="left",r="right",start="start",
  down="down",up="up",left="left",right="right"}}
local want = IDLE
emu.addEventCallback(function() pcall(emu.setInput, want, 0) end, emu.eventType.inputPolled)

local frame = 0
emu.addEventCallback(function() frame = frame + 1 end, emu.eventType.startFrame)

-- 句号跟踪(读句子指针 $87/$88 在 $F071 执行时)
local lastN, seq = -1, {{}}
emu.addMemoryCallback(function()
  local p = rd(0x87) + rd(0x88) * 256
  local n
  if p >= 0xBCB5 and p < 0xBFFF and rd(0xA000) == prg(0) then n = (p - 0xBCB5) // 3
  elseif p >= 0xA000 and p < 0xBD4B and rd(0xA000) == prg(0x2000) then n = (p - 0xA000) // 3 + 281 end
  if n and n ~= lastN then lastN = n; seq[#seq+1] = string.format("%d@%02X", n, rd(0x0450)) end
end, emu.callbackType.exec, 0xF071, 0xF071)

local LOADED = {("false" if start_state_hex else "true")}
local LOADED_AT = 0
local DONE, REPORTED = false, false

local co = coroutine.create(function()
  local function yield_frames(n) for _=1,(n or 1) do coroutine.yield() end end
  local function set(btn) local t={{}}; for k,v in pairs(IDLE) do t[k]=v end; if btn then t[KEY[btn]]=true end; want=t end
  local function tap(btn, hold, gap) set(btn); yield_frames(hold); set(nil); yield_frames(gap) end
  local function wait_ready(to)
    local w=0
    while rd(0x0200)~=0xF0 and rd(0x17)~=0x10 do coroutine.yield(); w=w+1; if w>(to or 900) then return false end end
    return true
  end
  -- 菜单原语($17是帧计数器非就绪标志,别等它):$2C=光标(0-based,子菜单也从0起), $0200==0xF0=对话翻页箭头
  local function page_ready(to) local w=0
    while rd(0x0200)~=0xF0 do coroutine.yield(); w=w+1; if w>(to or 150) then return false end end; return true end
  local function cursor_to(t) local tries=0
    while rd(0x2C)~=t and tries<24 do tap("down",4,12); tries=tries+1 end; return rd(0x2C)==t end
  local function choose(path)  -- path如 2,1 :逐级 光标到opt(1-based)→按A→推进随之对话,再选下一级
    for _,opt in ipairs(path) do
      cursor_to(opt-1); tap("a",4,18)
      -- 选完这级可能先播对话(问候等)才出下一级菜单:把对话推进到底再继续
      for _=1,40 do if not page_ready(70) then break end tap("a",4,12) end
    end
  end
  for _,act in ipairs(ACTIONS) do
    local base, rep = act, 1
    local star = act:find("%*")
    if star then base = act:sub(1,star-1); rep = tonumber(act:sub(star+1)) or 1 end
    for _=1,rep do
      if base=="start" then tap("start",4,40)
      elseif base=="a" then wait_ready(900); tap("a",4,10)
      elseif base=="A" then tap("A",4,10)
      elseif base=="adv" then
        -- 把当前对话推进到底:只在翻页箭头$0200==0xF0出现时按A;若120帧内不出现(=在菜单/无对话)则停,不误选
        for _=1,40 do
          local w=0
          while rd(0x0200)~=0xF0 do coroutine.yield(); w=w+1; if w>120 then break end end
          if rd(0x0200)~=0xF0 then break end
          tap("a",4,10)
        end
      elseif base=="d" then tap("d",4,10)
      elseif base=="u" then tap("u",4,10)
      elseif base=="l" then tap("l",4,10)
      elseif base=="r" then tap("r",4,10)
      elseif base=="b" then tap("b",4,10)
      elseif base=="shot" then print("MIDSHOT frame="..frame.." $0450="..rd(0x0450).." $2C="..rd(0x2C).." $17="..rd(0x17)); shot("mid"..frame)
      elseif base:match("^c[%d%.]+$") then
        -- cX.Y.Z:逐级菜单选择(1-based),选完把对话推到底
        local path={{}}; for num in base:sub(2):gmatch("%d+") do path[#path+1]=tonumber(num) end
        choose(path)
      elseif base:match("^w%d+$") then yield_frames(tonumber(base:sub(2)))
      end
    end
  end
  yield_frames({trail})
  DONE = true
end)

emu.addEventCallback(function()
  if LOADED and coroutine.status(co) ~= "dead" then
    local ok, err = coroutine.resume(co)
    if not ok then print("CORO_ERR: "..tostring(err)) end
  end
end, emu.eventType.startFrame)

-- 报告(存档须在 exec 回调内)
emu.addMemoryCallback(function()
{load_block}
  if (DONE or (LOADED and frame > LOADED_AT + 9000)) and not REPORTED then
    REPORTED = true
    if not DONE then print("!! 硬帧上限强制报告(动作可能卡住)") end
    shot("final")
    print(string.format("STATE frame=%d $0450=%02X $2C=%d $17=%02X $0200=%02X lastN=%d",
      frame, rd(0x0450), rd(0x2C), rd(0x17), rd(0x0200), lastN))
    print("SEQ "..table.concat(seq, " "))
    dump_savestate("end")
    emu.stop(0)
  end
end, emu.callbackType.exec, {NMI}, {NMI})
'''


def resolve_state(s):
    if s in (None, "none", ""):
        return None
    if s.endswith(".mss"):
        return mss_hex(s)
    return open(s).read().strip()  # .hex 文件


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="none")
    ap.add_argument("--actions", default="")
    ap.add_argument("--out", default=None)
    ap.add_argument("--shot", default=None)
    ap.add_argument("--trail", type=int, default=40)
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()

    start = resolve_state(a.state)
    actions = a.actions.split()
    lua = build_lua(start, actions, a.trail)
    here = os.path.dirname(os.path.abspath(__file__))
    rom = os.path.join(os.path.dirname(here), ROM)
    out = run_lua(lua, rom, timeout=a.timeout)

    # 非截图/blob 的普通输出
    for ln in out.splitlines():
        if ln.startswith(("STATE", "SEQ", "MIDSHOT")):
            print(ln)
    # 截图
    if a.shot:
        pngs = extract_pngs(out, os.path.dirname(os.path.abspath(a.shot)) or ".", prefix="_p")
        for tag, p in pngs:
            if tag == "final":
                os.replace(p, a.shot); print("SHOT ->", a.shot)
            else:
                dst = a.shot.replace(".png", f"_{tag}.png"); os.replace(p, dst); print("SHOT ->", dst)
    # 存档 blob
    if a.out:
        blob = extract_blob(out, "end")
        if blob:
            open(a.out, "w").write(blob); print(f"STATE_OUT -> {a.out} ({len(blob)//2} bytes)")
        else:
            print("!! 没拿到存档 blob(可能动作没跑完/超时)")


if __name__ == "__main__":
    main()
