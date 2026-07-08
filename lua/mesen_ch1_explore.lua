-- 第一章句集探索：句号 trace + 智能菜单遍历导航（借鉴 2021 自动化.lua 的 RAM 标志）。
-- RAM：$17==0x10 选项就绪 / $2C 选项光标 / $0200==0xF0 等翻页(▽)。
-- 策略：等翻页就按 A；菜单就绪就轮换选 0..4 号选项(按 down/up 对齐光标再 A)，
--       系统性遍历分支以跳出单场景循环，尽量覆盖第一章所有句子/场景。
-- 用法: Mesen --testrunner <rom> mesen_ch1_explore.lua > explore.log

local CPU = emu.memType.nesMemory
local PRG = emu.memType.nesPrgRom
local function rd(a) return emu.read(a, CPU) end
local function prg(off) return emu.read(off, PRG) end

local perbank = {}
local sentbank = {}    -- 句号 -> 首次出现时的背景 CG bank($0450)
local lastN = -1
local frame = 0
local count = 0

emu.addMemoryCallback(function()
  pcall(function()
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
      if not sentbank[n] then sentbank[n] = bank end
      perbank[bank] = perbank[bank] or {}
      perbank[bank][n] = true
    end
  end)
end, emu.callbackType.exec, 0xF071, 0xF071)

local IDLE = { a=false,b=false,select=false,start=false,up=false,down=false,left=false,right=false }
local function btn(name) local t={} for k,v in pairs(IDLE) do t[k]=v end t[name]=true return t end
local want = nil
emu.addEventCallback(function() pcall(emu.setInput, want or IDLE, 0) end, emu.eventType.inputPolled)

local cooldown = 0
local target = 0           -- 当前要选的选项号
local sinceSelect = 0      -- 距上次按 A 的帧数
emu.addEventCallback(function()
  frame = frame + 1
  want = nil
  if frame >= 3400 and frame < 3410 then want = btn("start"); return end
  if frame <= 3600 then return end

  if cooldown > 0 then cooldown = cooldown - 1; return end   -- 按键脉冲间隔

  local ready = rd(0x17)
  local waitpage = rd(0x0200)
  if waitpage == 0xF0 then
    want = btn("a"); cooldown = 6                            -- 翻页
  elseif ready == 0x10 then
    local cur = rd(0x2C)
    if cur < target then want = btn("down"); cooldown = 6
    elseif cur > target then want = btn("up"); cooldown = 6
    else
      want = btn("a"); cooldown = 10                         -- 选中当前项
      target = (target + 1) % 5                              -- 下次换一个选项(遍历分支)
    end
  else
    -- 非菜单/非翻页：偶尔按 A 推进纯对话
    if frame % 12 == 0 then want = btn("a"); cooldown = 8 end
  end

  if frame >= 45000 then
    -- 句→背景bank 映射(每句首次出现时的 $0450)
    local ns = {}
    for n in pairs(sentbank) do ns[#ns+1] = n end
    table.sort(ns)
    for _, n in ipairs(ns) do print(string.format("MAP\t%d\t%02X", n, sentbank[n])) end
    print(string.format("=== 覆盖 %d 个不同句号 ===", #ns))
    emu.stop(0)
  end
end, emu.eventType.startFrame)

pcall(emu.setEmulationSpeed, 0)
print("== 第一章探索启动 ==")
