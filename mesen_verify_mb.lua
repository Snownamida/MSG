-- 第一章确定性通关（移植自用户 2021 FCEUX "自动化.lua" 的 stage_1()）。
-- FCEUX 是命令式(emu.frameadvance 推进)，Mesen 是事件驱动——用协程桥接：
-- 每个 press/wait 用 coroutine.yield() 让出一帧；startFrame 里 resume 协程并更新输入；
-- setInput 在 inputPolled 回调里下发（Mesen 硬性要求）。
-- 同时挂句号 trace($F071 + $87)，记录每句首次出现时的背景 CG bank($0450)。
-- 用法: Mesen --testrunner <rom> mesen_ch1_playthrough.lua > play.log

local CPU = emu.memType.nesMemory
local PRG = emu.memType.nesPrgRom
local function rd(a) return emu.read(a, CPU) end
local function prg(o) return emu.read(o, PRG) end

-- ---- 句号 trace ----
local sentbank, order, lastN = {}, {}, -1
emu.addMemoryCallback(function()
  pcall(function()
    local p = rd(0x87) + rd(0x88) * 256
    local n
    if p >= 0xBCB5 and p < 0xBFFF and rd(0xA000) == prg(0) then n = (p - 0xBCB5) // 3
    elseif p >= 0xA000 and p < 0xBD4B and rd(0xA000) == prg(0x2000) then n = (p - 0xA000) // 3 + 281 end
    if n and n ~= lastN then
      lastN = n
      if not sentbank[n] then sentbank[n] = rd(0x0450); order[#order + 1] = n end
    end
  end)
end, emu.callbackType.exec, 0xF071, 0xF071)

-- ---- 输入 ----
local IDLE = { a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false }
local KEY = { A="a", B="b", up="up", down="down", left="left", right="right", start="start", select="select" }
local want = nil
emu.addEventCallback(function() pcall(emu.setInput, want or IDLE, 0) end, emu.eventType.inputPolled)
local function setbtn(name)
  local t = {}; for k, v in pairs(IDLE) do t[k] = v end
  if name then t[KEY[name] or name] = true end
  want = t
end

-- ---- 协程原语（对应 FCEUX 版函数）----
local frame = 0
local function fa() coroutine.yield() end                      -- emu.frameadvance
local function press(b) setbtn(b); fa(); setbtn(nil); fa() end  -- 按 1 帧 + 松 1 帧

local function wait_ready(exit_if_cant)                         -- wait_for_option_ready
  local timer = rd(0x9D)
  local waited = 0
  while rd(0x17) ~= 0x10 do
    fa(); waited = waited + 1
    if exit_if_cant and rd(0x9D) == (timer - 1) % 256 then return false end
    if waited > 1500 then return false end                     -- 死循环保护(序列走偏时放弃该步)
  end
  return true
end
local function press_opt(b, times) for _ = 1, times do wait_ready(); press(b) end end

local function wait_page()                                      -- 等翻页▽($0200==0xF0)，带超时保护
  local w = 0
  while rd(0x0200) ~= 0xF0 do
    fa(); w = w + 1; if w > 2000 then return false end
  end
  return true
end
local function next_para(times)                                -- next_para
  if type(times) == "number" then
    for _ = 1, times do if wait_page() then press("A") end end
  else                                                          -- 字符串 = "推进直到选项就绪"
    while wait_ready(true) == false do
      if not wait_page() then break end
      press("A")
    end
  end
end

local function option_view(opt, rep, dont_reset)               -- option_view
  for _ = 1, rep do
    local i = 1
    while opt[i] do
      wait_ready()
      local tries = 0
      while rd(0x2C) ~= opt[i] - 1 do
        press_opt("down", 1); wait_ready()
        tries = tries + 1; if tries > 12 then break end        -- 光标够不到目标就放弃
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

-- ---- stage_1()：地球篇=第一章（用户 2021 手调序列，原样搬运）----
local co = coroutine.create(function()
  while frame < 3300 do fa() end   -- 等开场动画播完到标题菜单
  press("start")                   -- 选 NEW GAME
  for _ = 1, 40 do fa() end

  next_para("to_next_option")
  -- 场景9
  option_view({1,1},2); option_view({1,2},2); option_view({2,1,1},1); option_view({2,2,1},2)
  option_view({3},1,true)
  option_view({1,1},2); option_view({1,2},2); option_view({2,1,1},2); option_view({2,2},2)
  option_view({3},2,true); option_view({3,1},1,true)
  -- 场景C
  option_view({1,1},2); option_view({1,2},3); option_view({2,1,1},4); option_view({2,1,2},2)
  option_view({3},1,true)
  -- 场景D
  option_view({3,3},1,true)
  -- 场景E
  option_view({1,1},2); option_view({1,2},1); option_view({2,1},1); option_view({2,1,1},2)
  option_view({2,1,2},1,true)
  press_opt("down",1); press_opt("A",1); next_para("to_next_option")
  option_view({1,1},1); option_view({2,1},1); option_view({2,2},1); option_view({1,2},1,true)
  press_opt("down",1); press_opt("A",1); next_para("to_next_option")
  press_opt("down",1); press_opt("A",1); next_para("to_next_option")
  press_opt("A",1); next_para("to_next_option")
  -- 上飞机
  option_view({1,1},2); option_view({1,2},1); option_view({1,3},1); option_view({2,1},1)
  option_view({2,2},1)
  press_opt("down",3); press_opt("A",1); next_para(1)
  wait_ready(); press_opt("A",1); wait_ready()
  option_view({3},1,true)
end)

-- ---- 驱动 + 收尾 ----
local function dump()
  print("=== 第一章句→背景bank（按到达顺序）===")
  for _, n in ipairs(order) do print(string.format("SEQ\t%d\t%02X", n, sentbank[n])) end
  local ns = {}
  for n in pairs(sentbank) do ns[#ns + 1] = n end
  table.sort(ns)
  print("SORTED\t" .. table.concat(ns, " "))
  print(string.format("=== 覆盖 %d 句 ===", #ns))
end

local done = false
local dumped = 0
emu.addEventCallback(function()
  frame = frame + 1
  -- [验证] 每个新出现的背景场景，检查 NMI 改造：$045F 应 == $0450|0x80
  do
    local cg = rd(0x0450)
    if not _scn then _scn = {} end
    if not _scn[cg] then
      _scn[cg] = true
      local fb = rd(0x045F)
      local exp = cg | 0x80
      print(string.format("VERIFY CG$%02X -> $045F=$%02X 期望$%02X %s", cg, fb, exp, fb==exp and "OK" or "MISMATCH"))
    end
    -- 对话框显示满、等翻页(▽ $0200==0xF0)时截图——文字最全；每场景截一次
    if not _shot then _shot = {} end
    if rd(0x0200) == 0xF0 and not _shot[cg] then
      _shot[cg] = true
      local ok, png = pcall(emu.takeScreenshot)
      if ok and type(png)=="string" then
        print(string.format("SHOT_%02X:%s", cg, (png:gsub(".", function(c) return string.format("%02x", c:byte()) end))))
      end
    end
  end
  -- 画面左上实时进度（GUI 可见）
  pcall(emu.drawString, 8, 8, string.format("CH1 trace: %d sentences  scene $%02X", #order, rd(0x0450)),
    0x00FF00, 0x000000, 3)
  if frame % 3000 == 0 then
    print(string.format("[f%d] co=%s $0450=%02X 句数=%d", frame, coroutine.status(co), rd(0x0450), #order))
    for i = dumped + 1, #order do
      local n = order[i]; print(string.format("SEQ\t%d\t%02X", n, sentbank[n]))
    end
    dumped = #order
  end
  if not done and coroutine.status(co) ~= "dead" then
    local ok, err = coroutine.resume(co)
    if not ok then print("协程错误@f" .. frame .. ": " .. tostring(err)); done = true; dump() end
  elseif not done then
    print("== stage_1 序列跑完 @f" .. frame .. " ==")
    done = true; dump()
    pcall(emu.displayMessage, "CH1", "通关序列跑完，映射已 dump 到 log")
  end
  -- GUI 模式无 testrunner 帧限；给个大上限防协程意外挂死
  if frame >= 200000 and not done then
    print("== 到达帧上限，dump 部分 ==")
    done = true; dump()
  end
end, emu.eventType.startFrame)

pcall(emu.setEmulationSpeed, 0)
print("== 第一章通关脚本启动 ==")
