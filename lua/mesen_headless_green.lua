-- 无头取证：自动进游戏到绿字画面，dump ExRAM(逐格bank/调色板)+nametable+MMC5寄存器。
-- 用法: Mesen --testrunner <rom> mesen_headless_green.lua > out.log
-- 输出经 print() 走 stdout（emu.log 在 testrunner 下不可见；io 被沙箱禁用）。
-- 截图以 "SHOT:<hex>" 行输出，shell 侧还原 PNG。
-- 目的：查明绿字区每个 tile 到底从哪个 CHR bank 取图（怀疑 MMC5 ExRAM 扩展属性模式）。

local frame = 0
local detected = -1
local dumped = false
local exram = {}
local regs = {}
local reglog = {}
local b12b = {}

local function scanline()
  local ok, st = pcall(emu.getState)
  if ok and st and st.ppu then return st.ppu.scanline end
  return -99
end

local lastw = {}
emu.addMemoryCallback(function(addr, value)
  regs[addr] = value
  if lastw[addr] ~= value then          -- 只记变化，防 $5105 刷屏
    lastw[addr] = value
    reglog[#reglog + 1] = string.format("f%d $%04X<-%02X", frame, addr, value)
    if #reglog > 600 then table.remove(reglog, 1) end
  end
  if addr == 0x512B then
    b12b[#b12b + 1] = { frame, value }
    if #b12b > 80 then table.remove(b12b, 1) end
  end
end, emu.callbackType.write, 0x5100, 0x5130)

emu.addMemoryCallback(function(addr, value)
  exram[addr] = value
end, emu.callbackType.write, 0x5C00, 0x5FFF)

local ppuType = nil
local function ppuread(a)
  if ppuType then
    local ok, v = pcall(emu.read, a, ppuType)
    if ok and v then return v end
  end
  for _, name in ipairs({ "nesPpuDebug", "ppuDebug", "nesPpuMemory", "ppuMemory" }) do
    local t = emu.memType and emu.memType[name]
    if t then
      local ok, v = pcall(emu.read, a, t)
      if ok and v then ppuType = t; return v end
    end
  end
  return 0
end

local function dumprow(base, row)
  local s = {}
  for c = 0, 31 do s[#s + 1] = string.format("%02X", ppuread(base + row * 32 + c) & 0xFF) end
  return table.concat(s, " ")
end

local function dump()
  print("=== 寄存器写入前 400 条 ===")
  for i = 1, #reglog do print(reglog[i]) end
  print("=== $512B 最近写入(帧/值) ===")
  for _, e in ipairs(b12b) do print(string.format("f%d val=%d", e[1], e[2])) end
  print("=== MMC5 寄存器终值 ===")
  local keys = {}
  for k in pairs(regs) do keys[#keys + 1] = k end
  table.sort(keys)
  for _, k in ipairs(keys) do print(string.format("$%04X = %02X", k, regs[k])) end
  for _, base in ipairs({ 0x2000, 0x2400 }) do
    print(string.format("=== NT $%04X 行0-29 ===", base))
    for r = 0, 29 do print(string.format("r%d: %s", r, dumprow(base, r))) end
  end
  for _, base in ipairs({ 0x23C0, 0x27C0 }) do
    print(string.format("=== 属性表 $%04X ===", base))
    for r = 0, 1 do print(dumprow(base, r)) end
  end
  print("=== 调色板 $3F00-$3F1F ===")
  print(dumprow(0x3F00, 0))
  print("=== ExRAM(CPU写入捕获) 行0-29 ===")
  for r = 0, 29 do
    local s = {}
    for c = 0, 31 do
      local v = exram[0x5C00 + r * 32 + c]
      s[#s + 1] = v and string.format("%02X", v) or ".."
    end
    print(string.format("r%d: %s", r, table.concat(s, " ")))
  end
  local n = 0
  for _ in pairs(exram) do n = n + 1 end
  print(string.format("ExRAM 共捕获 %d 字节写入", n))
  local ok, png = pcall(emu.takeScreenshot)
  if ok and type(png) == "string" then
    print("SHOT:" .. (png:gsub(".", function(c) return string.format("%02x", c:byte()) end)))
  else
    print("截图失败: " .. tostring(png))
  end
end

local IDLE = { a = false, b = false, select = false, start = false, up = false, down = false, left = false, right = false }
local function btn(name)
  local t = {}
  for k, v in pairs(IDLE) do t[k] = v end
  t[name] = true
  return t
end
local press = nil
emu.addEventCallback(function()
  frame = frame + 1
  pcall(emu.setInput, press or IDLE, 0)

  -- 检测连续码序列：汉化版 9B 50 F0（找创造）或原版 69 BC 56（は危き）
  if detected < 0 and frame % 3 == 0 then
    for r = 20, 29 do
      for c = 0, 28 do
        local a = 0x2000 + r * 32 + c
        local v1, v2, v3 = ppuread(a), ppuread(a + 1), ppuread(a + 2)
        if (v1 == 0x9B and v2 == 0x50 and v3 == 0xF0)
            or (v1 == 0x69 and v2 == 0xBC and v3 == 0x56) then
          detected = frame; press = nil
          print(string.format("== 帧%d 检测到绿字序列 @NT2000 r%d c%d (%02X %02X %02X) ==", frame, r, c, v1, v2, v3))
          local ok, png = pcall(emu.takeScreenshot)
          if ok and type(png) == "string" then
            print("PROGdet:" .. (png:gsub(".", function(ch) return string.format("%02x", ch:byte()) end)))
          end
          break
        end
      end
      if detected >= 0 then break end
    end
  end

  -- 开场动画在标题菜单之前自动播放（含绿字），什么都不按，等它出现
  press = nil

  if detected >= 0 and frame >= detected + 10 and not dumped then
    dumped = true
    dump()
    print("== 正常结束 ==")
    emu.stop(0)
  end
  if frame > 10000 and not dumped then
    dumped = true
    print("== 超时未检测到绿字，dump 当前状态 ==")
    dump()
    emu.stop(1)
  end
end, emu.eventType.startFrame)

pcall(emu.setEmulationSpeed, 0)   -- 不限速（若 API 存在）
print("== 无头取证启动 ==")
