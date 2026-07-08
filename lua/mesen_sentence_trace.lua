-- 句号 trace（移植自用户 2021 FCEUX 版"自动化.lua"的 print_sentence_number）：
-- 在 CPU 执行到 $F071 时，用 zero-page 指针 $87 反算游戏此刻正在显示的句号，
-- 同时记录背景 bank（RAM $0450）。配合随机按键推进剧情，输出"游戏实际读取的句号流"，
-- 用来测绘真实章节边界 + 每个场景(bank)用到的句集。
--
-- 关键（Mesen）：exec 回调必须传 start,end 两个地址（addMemoryCallback(fn,exec,a,a)）。
-- FCEUX→Mesen：rom.readbyte(0x10)→emu.read(0x00,nesPrgRom)；bank0 首字节=0x00，bank1=0x36。
-- 用法: Mesen --testrunner <rom> mesen_sentence_trace.lua > trace.log

local CPU = emu.memType.nesMemory
local PRG = emu.memType.nesPrgRom
local function rd(a) return emu.read(a, CPU) end
local function prg(off) return emu.read(off, PRG) end

local perbank = {}
local order = {}
local lastN = -1
local frame = 0
local count = 0

emu.addMemoryCallback(function()
  local okk = pcall(function()
    local p = rd(0x87) + rd(0x88) * 256
    local bank = rd(0x0450)
    local n = nil
    if p >= 0xBCB5 and p < 0xBFFF and rd(0xA000) == prg(0x00) then
      n = math.floor((p - 0xBCB5) / 3)
    elseif p >= 0xA000 and p < 0xBD4B and rd(0xA000) == prg(0x2000) then
      n = math.floor((p - 0xA000) / 3) + 281
    end
    if n and n ~= lastN then
      lastN = n
      count = count + 1
      if count <= 400 then print(string.format("SEQ\t%d\t%02X\tf%d", n, bank, frame)) end
      perbank[bank] = perbank[bank] or {}
      perbank[bank][n] = true
    end
  end)
end, emu.callbackType.exec, 0xF071, 0xF071)

local IDLE = { a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false }
local function btn(name) local t={} for k,v in pairs(IDLE) do t[k]=v end t[name]=true return t end
local want = nil
emu.addEventCallback(function() pcall(emu.setInput, want or IDLE, 0) end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  frame = frame + 1
  want = nil
  if frame >= 3400 and frame < 3410 then want = btn("start") end
  if frame > 3600 then
    local m = frame % 45
    if m < 4 then
      local k = math.floor(frame / 45)
      if k % 9 == 8 then want = btn("b")
      elseif k % 5 == 4 then want = btn("down")
      else want = btn("a") end
    end
  end
  if frame >= 18000 then
    print("=== 各 bank 用到的句集 ===")
    local banks = {}
    for b in pairs(perbank) do banks[#banks+1] = b end
    table.sort(banks)
    for _, b in ipairs(banks) do
      local ns = {}
      for n in pairs(perbank[b]) do ns[#ns+1] = n end
      table.sort(ns)
      print(string.format("BANK %02X (%d 句): %s", b, #ns, table.concat(ns, " ")))
    end
    print(string.format("=== 共 %d 次不同句号切换 ===", count))
    emu.stop(0)
  end
end, emu.eventType.startFrame)

pcall(emu.setEmulationSpeed, 0)
print("== 句号 trace 启动 ==")
