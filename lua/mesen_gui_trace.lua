-- GUI 场景映射 trace：在 Mesen GUI 里正常玩游戏，自动记录「每句 → 背景场景 bank($0450)」。
-- GUI 模式无 testrunner 的 30000 帧限，你随便玩多久都行。
-- 每遇到一个新句子，就在 Script 日志里打印一行 `SEQ  句号  场景bank`；玩完把这些行复制给我。
-- 画面左上角实时显示已记录句数，方便你知道它在干活。
--
-- 用法（Mesen GUI）：
--   1. 打开原版 ROM: Metal Slader Glory (Japan).nes
--   2. Debug 菜单 → Script Window（脚本窗口）
--   3. 打开本文件，点 Run（▶ / F5）
--   4. 正常玩第一章（新游戏→看完开场→一路玩到坐穿梭机离开地球）
--   5. 玩完后把日志区里所有 SEQ 行全选复制给我

local CPU = emu.memType.nesMemory
local PRG = emu.memType.nesPrgRom
local function rd(a) return emu.read(a, CPU) end
local function prg(o) return emu.read(o, PRG) end

local sentbank = {}   -- 句号 -> 首次出现时的背景 bank
local lastN = -1
local count = 0

-- 句号 trace 钩子（移植自 2021 自动化.lua 的 $F071 + $87 反算）
emu.addMemoryCallback(function()
  local p = rd(0x87) + rd(0x88) * 256
  local n
  if p >= 0xBCB5 and p < 0xBFFF and rd(0xA000) == prg(0) then
    n = (p - 0xBCB5) // 3
  elseif p >= 0xA000 and p < 0xBD4B and rd(0xA000) == prg(0x2000) then
    n = (p - 0xA000) // 3 + 281
  end
  if n and n ~= lastN then
    lastN = n
    if not sentbank[n] then
      sentbank[n] = rd(0x0450)
      count = count + 1
      emu.log(string.format("SEQ\t%d\t%02X", n, sentbank[n]))
    end
  end
end, emu.callbackType.exec, 0xF071, 0xF071)

-- 画面左上角实时进度
emu.addEventCallback(function()
  pcall(emu.drawString, 8, 8, string.format("scene-trace: %d sentences  (last #%d)", count, lastN),
    0x00FF00, 0x000000, 2)
end, emu.eventType.startFrame)

emu.log("== 场景 trace 已启动：正常玩第一章，玩完把所有 SEQ 行复制给我 ==")
