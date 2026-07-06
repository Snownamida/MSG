-- GUI 自动通关 + 场景映射 trace（在 Mesen GUI 里跑，无 30000 帧限）。
-- 自动倍速跑 stage_1 通关序列；跑到海边那段(stage_1 本身没调好)会卡住，自动切「手动模式」
-- 把控制权交还给你——你手动接管玩到第一章结束即可。trace 是被动钩子，不管谁按键全程都记录。
--
-- 用法（Mesen GUI）：
--   1. 打开原版 ROM: Metal Slader Glory (Japan).nes
--   2. Debug 菜单 → Script Window，打开本文件，点 Run
--   3. 它自动开新游戏、看完开场、倍速跑到海边
--   4. 画面左上显示状态：AUTO(脚本自动跑) / MANUAL(卡住了，请你手动接管)
--   5. 变红 MANUAL 后，你手动玩到坐穿梭机离开地球(第一章结束)；trace 一直在记录
--   6. 玩完把日志区所有 SEQ 行复制给我 → 我就能 build 完整第一章
--   速度可用 Mesen 的 Emulation Speed 菜单/快捷键随时调（脚本默认设 3x；卡住手动时可调回正常速）

pcall(emu.setEmulationSpeed, 300)   -- 3x；你可在 GUI 里再调

local CPU = emu.memType.nesMemory
local PRG = emu.memType.nesPrgRom
local function rd(a) return emu.read(a, CPU) end
local function prg(o) return emu.read(o, PRG) end

-- ---- 场景映射 trace（被动记录，不管按键来源）----
local sentbank, lastN, count = {}, -1, 0
emu.addMemoryCallback(function()
  local p = rd(0x87) + rd(0x88) * 256
  local n
  if p >= 0xBCB5 and p < 0xBFFF and rd(0xA000) == prg(0) then n = (p - 0xBCB5) // 3
  elseif p >= 0xA000 and p < 0xBD4B and rd(0xA000) == prg(0x2000) then n = (p - 0xA000) // 3 + 281 end
  if n and n ~= lastN then
    lastN = n
    if not sentbank[n] then
      sentbank[n] = rd(0x0450); count = count + 1
      emu.log(string.format("SEQ\t%d\t%02X", n, sentbank[n]))
    end
  end
end, emu.callbackType.exec, 0xF071, 0xF071)

-- ---- 输入：AUTO 时脚本下发；MANUAL 时不覆盖(你的手柄/键盘直接控制) ----
local IDLE = { a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false }
local KEY = { A="a", B="b", up="up", down="down", left="left", right="right", start="start", select="select" }
local want, manual = nil, false
emu.addEventCallback(function()
  if not manual then pcall(emu.setInput, want or IDLE, 0) end
end, emu.eventType.inputPolled)
local function setbtn(name)
  local t = {}; for k, v in pairs(IDLE) do t[k] = v end
  if name then t[KEY[name] or name] = true end
  want = t
end

-- ---- 协程原语 ----
local frame = 0
local function fa() coroutine.yield() end
local function press(b) setbtn(b); fa(); setbtn(nil); fa() end
local stall = 0    -- 连续超时计数（用于触发 MANUAL）
local function wait_ready(exit_if_cant)
  local timer = rd(0x9D); local w = 0
  while rd(0x17) ~= 0x10 do
    fa(); w = w + 1
    if exit_if_cant and rd(0x9D) == (timer - 1) % 256 then return false end
    if w > 1200 then stall = stall + 1; return false end
  end
  stall = 0
  return true
end
local function press_opt(b, times) for _ = 1, times do wait_ready(); press(b) end end
local function wait_page()
  local w = 0
  while rd(0x0200) ~= 0xF0 do fa(); w = w + 1; if w > 1800 then return false end end
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

-- ---- stage_1 序列 ----
local co = coroutine.create(function()
  while frame < 3300 do fa() end
  press("start"); for _ = 1, 40 do fa() end
  next_para("to_next_option")
  option_view({1,1},2); option_view({1,2},2); option_view({2,1,1},1); option_view({2,2,1},2)
  option_view({3},1,true)
  option_view({1,1},2); option_view({1,2},2); option_view({2,1,1},2); option_view({2,2},2)
  option_view({3},2,true); option_view({3,1},1,true)
  option_view({1,1},2); option_view({1,2},3); option_view({2,1,1},4); option_view({2,1,2},2)
  option_view({3},1,true)
  option_view({3,3},1,true)
  option_view({1,1},2); option_view({1,2},1); option_view({2,1},1); option_view({2,1,1},2)
  option_view({2,1,2},1,true)
  press_opt("down",1); press_opt("A",1); next_para("to_next_option")
  option_view({1,1},1); option_view({2,1},1); option_view({2,2},1); option_view({1,2},1,true)
  press_opt("down",1); press_opt("A",1); next_para("to_next_option")
  press_opt("down",1); press_opt("A",1); next_para("to_next_option")
  press_opt("A",1); next_para("to_next_option")
  option_view({1,1},2); option_view({1,2},1); option_view({1,3},1); option_view({2,1},1)
  option_view({2,2},1)
  press_opt("down",3); press_opt("A",1); next_para(1)
  wait_ready(); press_opt("A",1); wait_ready()
  option_view({3},1,true)
end)

-- ---- 驱动：卡住(连续超时≥3)→MANUAL交还控制；剧情推进(有新句)→自动恢复AUTO ----
local lastCount, idleFrames = 0, 0
emu.addEventCallback(function()
  frame = frame + 1
  pcall(emu.drawString, 8, 8,
    string.format("%s  %d sentences (last #%d)", manual and "MANUAL(请手动推剧情)" or "AUTO", count, lastN),
    manual and 0xFF4040 or 0x00FF00, 0x000000, 2)

  if not manual then
    if coroutine.status(co) ~= "dead" then
      local ok, err = coroutine.resume(co)
      if not ok then emu.log("协程错误: " .. tostring(err)) end
    end
    if stall >= 3 then manual = true; stall = 0; emu.log("== 卡住，切 MANUAL：请手动推剧情 ==") end
  else
    -- 手动模式下若剧情在推进(有新句)，保持手动；若你已推过一段(句数涨了不少)可继续手动到章末
    if count > lastCount then idleFrames = 0 else idleFrames = idleFrames + 1 end
  end
  lastCount = count
end, emu.eventType.startFrame)

emu.log("== GUI 自动通关+trace 启动：AUTO 跑，卡住会切 MANUAL 交还给你 ==")
