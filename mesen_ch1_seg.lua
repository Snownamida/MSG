-- 第一章分段通关（突破 MesenCE testrunner 30000 帧上限）：
-- stage_1 序列拆成操作列表 ops[]，段边界落在操作之间。每段跑到 SEG_LIMIT 帧就在 op 边界
-- createSavestate（4KB）+ print(STEP, STATE hex)；下段脚本内嵌该 hex，loadSavestate 续跑。
-- 句号 trace 累积输出 SEQ 行，各段 shell 侧合并。
-- 占位由 drive_segments.py 替换：__START__（起始 op 序号）、__STATE__（上段 savestate hex，段1为空）。

local START = __START__
local STATE_HEX = "__STATE__"
local SEG_LIMIT = 19000

local CPU = emu.memType.nesMemory
local PRG = emu.memType.nesPrgRom
local function rd(a) return emu.read(a, CPU) end
local function prg(o) return emu.read(o, PRG) end

-- ---- 句号 trace ----
local sentbank, order, lastN = {}, {}, -1
local function trace()
  local p = rd(0x87) + rd(0x88) * 256
  local n
  if p >= 0xBCB5 and p < 0xBFFF and rd(0xA000) == prg(0) then n = (p - 0xBCB5) // 3
  elseif p >= 0xA000 and p < 0xBD4B and rd(0xA000) == prg(0x2000) then n = (p - 0xA000) // 3 + 281 end
  if n and n ~= lastN then
    lastN = n
    if not sentbank[n] then sentbank[n] = rd(0x0450); order[#order + 1] = n; print(string.format("SEQ\t%d\t%02X", n, sentbank[n])) end
  end
end

-- ---- 输入（inputPolled 下发）----
local IDLE = { a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false }
local KEY = { A="a", B="b", up="up", down="down", left="left", right="right", start="start", select="select" }
local want = nil
emu.addEventCallback(function() pcall(emu.setInput, want or IDLE, 0) end, emu.eventType.inputPolled)
local function setbtn(name)
  local t = {}; for k, v in pairs(IDLE) do t[k] = v end
  if name then t[KEY[name] or name] = true end
  want = t
end

-- ---- 协程原语 ----
local frame = 0
local function fa() coroutine.yield() end
local function press(b) setbtn(b); fa(); setbtn(nil); fa() end
local function wait_ready(exit_if_cant)
  local timer = rd(0x9D); local w = 0
  while rd(0x17) ~= 0x10 do
    fa(); w = w + 1
    if exit_if_cant and rd(0x9D) == (timer - 1) % 256 then return false end
    if w > 1500 then return false end
  end
  return true
end
local function press_opt(b, times) for _ = 1, times do wait_ready(); press(b) end end
local function wait_page()
  local w = 0
  while rd(0x0200) ~= 0xF0 do fa(); w = w + 1; if w > 2000 then return false end end
  return true
end
local function next_para(times)
  if type(times) == "number" then
    for _ = 1, times do if wait_page() then press("A") end end
  else
    while wait_ready(true) == false do
      if not wait_page() then break end
      press("A")
    end
  end
end
local function option_view(opt, rep, dont_reset)
  for _ = 1, rep do
    local i = 1
    while opt[i] do
      wait_ready()
      local tries = 0
      while rd(0x2C) ~= opt[i] - 1 do
        press_opt("down", 1); wait_ready(); tries = tries + 1; if tries > 12 then break end
      end
      press_opt("A", 1); i = i + 1
    end
    i = i - 1
    next_para("to_next_option")
    if not dont_reset then
      while opt[i] do
        wait_ready()
        while rd(0x2C) ~= 0x00 do press_opt("up", 1); wait_ready() end
        press_opt("B", 1); i = i - 1
      end
    end
  end
end

-- ---- stage_1 操作列表（每项一个操作，段边界落在项之间）----
local ops = {
  function() next_para("to_next_option") end,
  function() option_view({1,1},2) end, function() option_view({1,2},2) end,
  function() option_view({2,1,1},1) end, function() option_view({2,2,1},2) end,
  function() option_view({3},1,true) end,
  function() option_view({1,1},2) end, function() option_view({1,2},2) end,
  function() option_view({2,1,1},2) end, function() option_view({2,2},2) end,
  function() option_view({3},2,true) end, function() option_view({3,1},1,true) end,
  function() option_view({1,1},2) end, function() option_view({1,2},3) end,
  function() option_view({2,1,1},4) end, function() option_view({2,1,2},2) end,
  function() option_view({3},1,true) end,
  function() option_view({3,3},1,true) end,
  function() option_view({1,1},2) end, function() option_view({1,2},1) end,
  function() option_view({2,1},1) end, function() option_view({2,1,1},2) end,
  function() option_view({2,1,2},1,true) end,
  function() press_opt("down",1); press_opt("A",1); next_para("to_next_option") end,
  function() option_view({1,1},1) end, function() option_view({2,1},1) end,
  function() option_view({2,2},1) end, function() option_view({1,2},1,true) end,
  function() press_opt("down",1); press_opt("A",1); next_para("to_next_option") end,
  function() press_opt("down",1); press_opt("A",1); next_para("to_next_option") end,
  function() press_opt("A",1); next_para("to_next_option") end,
  function() option_view({1,1},2) end, function() option_view({1,2},1) end,
  function() option_view({1,3},1) end, function() option_view({2,1},1) end,
  function() option_view({2,2},1) end,
  function() press_opt("down",3); press_opt("A",1); next_para(1) end,
  function() wait_ready(); press_opt("A",1); wait_ready() end,
  function() option_view({3},1,true) end,
}

local step = START - 1
local co = coroutine.create(function()
  if STATE_HEX == "" then                        -- 段1：从开场进游戏
    while frame < 3300 do fa() end
    press("start"); for _ = 1, 40 do fa() end
  end
  for i = START, #ops do
    ops[i]()
    step = i
    if frame > SEG_LIMIT then coroutine.yield("SEG") end
  end
  coroutine.yield("DONE")
end)

-- ---- 驱动 ----
local loaded = (STATE_HEX == "")
local phase = nil                                -- "SEG"/"DONE" pending savestate
local function tohex(s) return (s:gsub(".", function(c) return string.format("%02x", c:byte()) end)) end
local function fromhex(s) return (s:gsub("..", function(cc) return string.char(tonumber(cc, 16)) end)) end

emu.addMemoryCallback(function()
  if not loaded then
    loaded = true
    pcall(emu.loadSavestate, fromhex(STATE_HEX))
    return
  end
  trace()
  if phase then
    local ok, st = pcall(emu.createSavestate)
    if phase == "SEG" and ok and type(st) == "string" then
      print("STEP\t" .. step)
      print("STATE\t" .. tohex(st))
    end
    print(phase == "DONE" and "== DONE ==" or "== SEG ==")
    emu.stop(0)
  end
end, emu.callbackType.exec, 0xF071, 0xF071)

emu.addEventCallback(function()
  frame = frame + 1
  if frame % 3000 == 0 then
    print(string.format("PROG f%d step=%d co=%s $17=%02X $2C=%02X $0200=%02X $0450=%02X 句=%d",
      frame, step, coroutine.status(co), rd(0x17), rd(0x2C), rd(0x0200), rd(0x0450), #order))
  end
  if not loaded then return end                  -- 等 exec callback load 完
  if coroutine.status(co) ~= "dead" and not phase then
    local ok, val = coroutine.resume(co)
    if not ok then print("协程错误: " .. tostring(val)); phase = "DONE" end
    if val == "SEG" or val == "DONE" then phase = val end
  end
  if frame > 32000 and not phase then phase = "SEG" end   -- 兜底
end, emu.eventType.startFrame)

print("== 段启动 START=" .. START .. " has_state=" .. tostring(STATE_HEX ~= "") .. " ==")
