-- 准确 trace：每帧采样(当前句 lastN, 背景场景 $0450)，累积「句 → 它显示期间出现过的所有 $0450」。
-- 这修正了旧 trace 只在 $F071 读指针时刻记 $0450 的问题——跨 CG 的句会被记成集合，而非单一场景。
-- 自动跑 stage_1（testrunner 前段能覆盖开场+海边+店门口，即当前乱码区）。
-- 输出 MAP 行：句号 场景1,场景2,...（多场景=跨CG句，装箱需在这些 bank 都放字）。

local CPU = emu.memType.nesMemory
local PRG = emu.memType.nesPrgRom
local function rd(a) return emu.read(a, CPU) end
local function prg(o) return emu.read(o, PRG) end

local sc = {}       -- 句 -> { $0450 -> true }
local order = {}
local lastN = -1
emu.addMemoryCallback(function()
  local p = rd(0x87) + rd(0x88) * 256
  local n
  if p >= 0xBCB5 and p < 0xBFFF and rd(0xA000) == prg(0) then n = (p - 0xBCB5) // 3
  elseif p >= 0xA000 and p < 0xBD4B and rd(0xA000) == prg(0x2000) then n = (p - 0xA000) // 3 + 281 end
  if n then lastN = n end
end, emu.callbackType.exec, 0xF071, 0xF071)

-- 输入 & stage_1（同 playthrough）
local IDLE = { a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false }
local KEY = { A="a", B="b", up="up", down="down", left="left", right="right", start="start", select="select" }
local want = nil
emu.addEventCallback(function() pcall(emu.setInput, want or IDLE, 0) end, emu.eventType.inputPolled)
local function setbtn(name)
  local t = {}; for k, v in pairs(IDLE) do t[k] = v end
  if name then t[KEY[name] or name] = true end
  want = t
end
local frame = 0
local function fa() coroutine.yield() end
local function press(b) setbtn(b); fa(); setbtn(nil); fa() end
local function wait_ready(e) local tm=rd(0x9D); local w=0
  while rd(0x17)~=0x10 do fa(); w=w+1; if e and rd(0x9D)==(tm-1)%256 then return false end; if w>1200 then return false end end; return true end
local function press_opt(b,t) for _=1,t do wait_ready(); press(b) end end
local function wait_page() local w=0; while rd(0x0200)~=0xF0 do fa(); w=w+1; if w>1800 then return false end end; return true end
local function next_para(t)
  if type(t)=="number" then for _=1,t do if wait_page() then press("A") end end
  else while wait_ready(true)==false do if not wait_page() then break end; press("A") end end end
local function option_view(opt,rep,dr)
  for _=1,rep do local i=1
    while opt[i] do wait_ready(); local tr=0
      while rd(0x2C)~=opt[i]-1 do press_opt("down",1); wait_ready(); tr=tr+1; if tr>12 then break end end
      press_opt("A",1); i=i+1 end
    i=i-1; next_para("to_next_option")
    if not dr then while opt[i] do wait_ready(); while rd(0x2C)~=0 do press_opt("up",1); wait_ready() end; press_opt("B",1); i=i-1 end end
  end end

local co = coroutine.create(function()
  while frame < 3300 do fa() end
  press("start"); for _=1,40 do fa() end
  next_para("to_next_option")
  option_view({1,1},2); option_view({1,2},2); option_view({2,1,1},1); option_view({2,2,1},2); option_view({3},1,true)
  option_view({1,1},2); option_view({1,2},2); option_view({2,1,1},2); option_view({2,2},2); option_view({3},2,true); option_view({3,1},1,true)
  option_view({1,1},2); option_view({1,2},3); option_view({2,1,1},4); option_view({2,1,2},2); option_view({3},1,true)
  option_view({3,3},1,true)
  option_view({1,1},2); option_view({1,2},1); option_view({2,1},1); option_view({2,1,1},2); option_view({2,1,2},1,true)
  press_opt("down",1); press_opt("A",1); next_para("to_next_option")
end)

local dumped = false
emu.addEventCallback(function()
  frame = frame + 1
  if coroutine.status(co) ~= "dead" then pcall(coroutine.resume, co) end
  if lastN > 0 then
    local b = rd(0x0450)
    if not sc[lastN] then sc[lastN] = {}; order[#order+1] = lastN end
    sc[lastN][b] = true
  end
  if frame >= 26000 and not dumped then
    dumped = true
    table.sort(order)
    for _, n in ipairs(order) do
      local bs = {}
      for b in pairs(sc[n]) do bs[#bs+1] = string.format("%02X", b) end
      table.sort(bs)
      print("MAP\t" .. n .. "\t" .. table.concat(bs, ","))
    end
    print("== 准确 trace 完成 ==")
    emu.stop(0)
  end
end, emu.eventType.startFrame)
pcall(emu.setEmulationSpeed, 0)
