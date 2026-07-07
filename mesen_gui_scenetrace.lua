-- GUI「自动玩 + 卡了你接管 + 全程被动场景采样」。
-- 目的：记录第一章每句显示期间经过的所有背景场景 $0450，用于精准修掉所有跨场景乱码。
-- GUI 无 30000 帧限。脚本会自动玩，卡住时画面变红 MANUAL——你手动推进剧情几下即可，
-- 能自动就继续自动。全程被动记录（不管 AUTO 还是你手动都记）。
--
-- 用法（Mesen GUI）：
--   1. 打开 ROM：MSG-zh-demo.nes（汉化版；原版也行，句号一致）
--   2. Debug → Script Window，打开本文件，Run
--   3. 看它自动玩。变红 MANUAL 时你接管，把剧情往下推（新游戏→开场→海边→查米店→
--      工作间→穿梭机…一路到坐穿梭机离开地球=第一章结束）。多进命令菜单、多对话。
--   4. 玩到章末(或想输出时)按一下手柄 SELECT → 日志区打出所有 MAP 行
--   5. 把日志区所有 MAP 行复制给我
-- 画面左上实时显示 AUTO/MANUAL + 已采样句数。

local CPU = emu.memType.nesMemory
local PRG = emu.memType.nesPrgRom
local function rd(a) return emu.read(a, CPU) end
local function prg(o) return emu.read(o, PRG) end

-- ---- 场景采样（被动，全程记录）----
local scene, order, lastN = {}, {}, -1
emu.addMemoryCallback(function()
  local p = rd(0x87) + rd(0x88) * 256
  local n
  if p >= 0xBCB5 and p < 0xBFFF and rd(0xA000) == prg(0) then n = (p - 0xBCB5) // 3
  elseif p >= 0xA000 and p < 0xBD4B and rd(0xA000) == prg(0x2000) then n = (p - 0xA000) // 3 + 281 end
  if n then lastN = n end
end, emu.callbackType.exec, 0xF071, 0xF071)

local function dump()
  table.sort(order)
  emu.log("==== 场景采样结果（复制以下所有 MAP 行给我）====")
  for _, n in ipairs(order) do
    local bs = {}
    for b in pairs(scene[n]) do bs[#bs + 1] = string.format("%02X", b) end
    table.sort(bs)
    emu.log(string.format("MAP\t%d\t%s", n, table.concat(bs, ",")))
  end
  emu.log(string.format("==== 共 %d 句 ====", #order))
end

-- ---- 输入：AUTO 时脚本下发；MANUAL 时不覆盖(你的手柄直接控制) ----
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
local stall = 0
local function wait_ready(exit_if_cant)
  local timer = rd(0x9D); local w = 0
  while rd(0x17) ~= 0x10 do
    fa(); w = w + 1
    if exit_if_cant and rd(0x9D) == (timer - 1) % 256 then return false end
    if w > 1200 then stall = stall + 1; return false end
  end
  stall = 0; return true
end
local function press_opt(b, times) for _ = 1, times do wait_ready(); press(b) end end
local function wait_page() local w = 0
  while rd(0x0200) ~= 0xF0 do fa(); w = w + 1; if w > 1800 then return false end end; return true end
local function next_para(times)
  if type(times) == "number" then for _ = 1, times do if wait_page() then press("A") end end
  else while wait_ready(true) == false do if not wait_page() then break end; press("A") end end
end
local function option_view(opt, rep, dont_reset)
  for _ = 1, rep do local i = 1
    while opt[i] do wait_ready(); local tries = 0
      while rd(0x2C) ~= opt[i] - 1 do press_opt("down", 1); wait_ready(); tries = tries + 1; if tries > 12 then break end end
      press_opt("A", 1); i = i + 1 end
    i = i - 1; next_para("to_next_option")
    if not dont_reset then while opt[i] do wait_ready(); while rd(0x2C) ~= 0 do press_opt("up",1); wait_ready() end; press_opt("B",1); i=i-1 end end
  end
end

-- ---- stage_1 自动序列（尽量玩远；卡住会切 MANUAL 交给你）----
local co = coroutine.create(function()
  while frame < 3300 do fa() end
  press("start"); for _ = 1, 40 do fa() end
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
  -- 后续(工作间/穿梭机)走不通就切 MANUAL 交给你
end)

local dumped_at = 0
emu.addEventCallback(function()
  frame = frame + 1
  if lastN > 0 then
    local b = rd(0x0450)
    if not scene[lastN] then scene[lastN] = {}; order[#order + 1] = lastN end
    scene[lastN][b] = true
  end
  if not manual then
    if coroutine.status(co) ~= "dead" then
      pcall(coroutine.resume, co)
      if stall >= 3 then manual = true; stall = 0; emu.log("== 卡住，切 MANUAL：请手动把剧情往下推 ==") end
    else manual = true; emu.log("== 自动序列跑完，切 MANUAL：请手动玩到章末，按 SELECT 输出 ==") end
  end
  pcall(emu.drawString, 8, 8, string.format("%s  %d sentences (last #%d)  [SELECT=输出]",
    manual and "MANUAL(请手动推进)" or "AUTO", #order, lastN), manual and 0xFF4040 or 0x00FF00, 0x000000)
  local ok, pad = pcall(emu.getInput, 0)
  if ok and pad and pad.select and (emu.getState()["ppu.frameCount"] - dumped_at > 120) then
    dumped_at = emu.getState()["ppu.frameCount"]; dump()
  end
end, emu.eventType.startFrame)

emu.log("== 自动玩+采样启动：AUTO 跑，卡住变红请接管；按 SELECT 输出 MAP ==")
